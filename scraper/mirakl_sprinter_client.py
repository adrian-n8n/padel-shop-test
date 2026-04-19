#!/usr/bin/env python3
"""
Mirakl Sprinter Client
=======================
Gestiona ofertas en el marketplace de Sprinter (sprinter-prod.mirakl.net)
usando la API de Mirakl (OF01 / OF02).

Flujo principal:
  1. Leer productos de Shopify (por EAN/barcode)
  2. Crear/actualizar ofertas en Mirakl via PUT /api/offers (OF01)
  3. Consultar estado de oferta via GET /api/offers

Uso directo:
    python mirakl_sprinter_client.py --list              # listar ofertas activas
    python mirakl_sprinter_client.py --upload 10016306954582  # subir producto Shopify por ID
    python mirakl_sprinter_client.py --status <shop_sku> # estado de una oferta
"""

import argparse
import csv
import io
import json
import os
import sys
import time
from pathlib import Path

import requests
from dotenv import load_dotenv

ENV_PATH = Path(__file__).parent / ".env"
load_dotenv(dotenv_path=ENV_PATH)

MIRAKL_BASE_URL = os.getenv("MIRAKL_BASE_URL", "https://sprinter-prod.mirakl.net")
MIRAKL_API_KEY  = os.getenv("MIRAKL_API_KEY", "")
SHOPIFY_STORE   = os.getenv("SHOPIFY_STORE", "utrsp8-0c.myshopify.com").rstrip("/")
SHOPIFY_TOKEN   = os.getenv("SHOPIFY_TOKEN", "")
API_VERSION     = "2025-01"

# Estado de condición: 11 = Nuevo (requerido por Sprinter)
OFFER_STATE     = "11"
# Tiempo de envío en días hábiles
LEADTIME_TO_SHIP = 2


def mirakl_headers() -> dict:
    return {"Authorization": MIRAKL_API_KEY, "Accept": "application/json"}


def shopify_headers() -> dict:
    return {
        "X-Shopify-Access-Token": SHOPIFY_TOKEN,
        "Content-Type": "application/json",
    }


# ── Shopify helpers ────────────────────────────────────────────────────────────

def get_shopify_product(product_id: str) -> dict:
    url = f"https://{SHOPIFY_STORE}/admin/api/{API_VERSION}/products/{product_id}.json"
    r = requests.get(url, headers=shopify_headers(), timeout=20)
    r.raise_for_status()
    return r.json()["product"]


def get_shopify_inventory(inventory_item_id: str) -> int:
    """Devuelve el stock total disponible."""
    url = f"https://{SHOPIFY_STORE}/admin/api/{API_VERSION}/inventory_levels.json"
    r = requests.get(url, headers=shopify_headers(),
                     params={"inventory_item_ids": inventory_item_id}, timeout=20)
    r.raise_for_status()
    levels = r.json().get("inventory_levels", [])
    return sum(l.get("available", 0) or 0 for l in levels)


# ── Mirakl helpers ─────────────────────────────────────────────────────────────

def list_offers(max_results: int = 50, offset: int = 0) -> dict:
    """GET /api/offers — lista las ofertas del vendedor."""
    r = requests.get(
        f"{MIRAKL_BASE_URL}/api/offers",
        headers=mirakl_headers(),
        params={"max": max_results, "offset": offset},
        timeout=30,
    )
    r.raise_for_status()
    return r.json()


def list_all_offers() -> list:
    """Pagina todas las ofertas y las devuelve."""
    offers = []
    offset = 0
    limit  = 100
    while True:
        data  = list_offers(max_results=limit, offset=offset)
        batch = data.get("offers", [])
        offers.extend(batch)
        total = data.get("total_count", 0)
        offset += limit
        if offset >= total or not batch:
            break
        time.sleep(0.3)
    return offers


def get_offer_by_shop_sku(shop_sku: str) -> dict:
    """Busca una oferta por shop_sku."""
    r = requests.get(
        f"{MIRAKL_BASE_URL}/api/offers",
        headers=mirakl_headers(),
        params={"shop_sku": shop_sku, "max": 1},
        timeout=20,
    )
    r.raise_for_status()
    offers = r.json().get("offers", [])
    return offers[0] if offers else None


def build_offer_csv(offers: list) -> str:
    """
    Construye el CSV en formato OF01 de Mirakl.
    Campos requeridos: ean, shop-sku, price, quantity, state, leadtime-to-ship
    """
    fieldnames = [
        "sku",
        "product-id",
        "product-id-type",
        "price",
        "price-additional-info",
        "quantity",
        "state",
        "leadtime-to-ship",
        "description",
    ]
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=fieldnames, delimiter=";",
                            extrasaction="ignore", lineterminator="\n")
    writer.writeheader()
    for o in offers:
        # mapear shop-sku → sku para el CSV
        row = dict(o)
        row["sku"] = row.pop("shop-sku", row.get("sku", ""))
        writer.writerow(row)
    return buf.getvalue()


def import_offers(offers: list) -> dict:
    """
    POST /api/offers/imports (OF01) — multipart/form-data con CSV.
    Devuelve import_id para hacer seguimiento.
    """
    csv_content = build_offer_csv(offers)
    r = requests.post(
        f"{MIRAKL_BASE_URL}/api/offers/imports",
        headers={"Authorization": MIRAKL_API_KEY},
        files={"file": ("offers.csv", csv_content.encode("utf-8"), "text/csv")},
        data={"import_mode": "NORMAL"},
        timeout=60,
    )
    r.raise_for_status()
    return r.json()


def get_import_status(import_id: str) -> dict:
    """Consulta el estado de un import (OF02): GET /api/offers/imports/{id}."""
    r = requests.get(
        f"{MIRAKL_BASE_URL}/api/offers/imports/{import_id}",
        headers=mirakl_headers(),
        timeout=20,
    )
    r.raise_for_status()
    return r.json()


def get_import_error_report(import_id: str) -> str:
    """Descarga el reporte de errores de un import."""
    r = requests.get(
        f"{MIRAKL_BASE_URL}/api/offers/imports/{import_id}/error_report",
        headers=mirakl_headers(),
        timeout=20,
    )
    r.raise_for_status()
    return r.text


def wait_for_import(import_id: str, timeout: int = 120) -> dict:
    """Espera hasta que el import termine (OF02 status: COMPLETE/FAILED)."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        status = get_import_status(import_id)
        state  = status.get("status", "")
        lines_ok  = status.get("lines_in_success", 0)
        lines_err = status.get("lines_in_error", 0)
        print(f"  Import {import_id}: {state} (ok={lines_ok}, err={lines_err})")
        if state in ("COMPLETE", "FAILED"):
            return status
        time.sleep(4)
    return {"status": "TIMEOUT"}


# ── Creación de producto en catálogo Mirakl (P21) ─────────────────────────────

PRODUCT_FIELDS = [
    "categorias", "sku-de-vendedor", "nombre-del-articulo", "nombre-del-articulo-pt",
    "subtitulo-de-productos", "pais-fabricante", "marcas", "genero", "ean",
    "descripion-del-producto", "cuidados", "imagenes-1", "imagenes-2", "imagenes-3",
    "imagenes-4", "video", "guia-de-tallas", "cuidados-pt", "descripion-del-producto-pt",
    "pais-fabricante-pt", "subtitulo-de-productos-pt", "nombre-del-fabricante",
    "nombre-comercial-registrado-del-fabricante", "direccion-del-fabricante",
    "correo-electronico-del-fabricante", "nombre-persona-responsable-en-eu",
    "direccion-de-la-persona-responsable", "correo-electronico-de-la-persona-responsable",
    "foto-etiqueta-del-producto", "manual-de-seguridad-del-producto", "model",
    "colores", "talla", "colecciones", "material-composicion", "variant_group_code",
    "consejos-de-utilizacion", "impermeable", "informacion-tecnica",
    "consejos-de-utilizacion-pt", "informacion-tecnica-pt", "material-composicion-pt",
    "colecciones-pt",
]

CATEGORY_MAP = {
    "palas de padel": "equipamiento_accesorios-padel-palas",
    "palas de pádel": "equipamiento_accesorios-padel-palas",
    "paleteros":      "equipamiento_accesorios-padel-paleteros",
    "pelotas padel":  "equipamiento_accesorios-padel-pelotas",
    "calzado padel":  "calzado-padel",
    "ropa":           "equipamiento_accesorios-padel",
}

def guess_category(product_type: str) -> str:
    pt = (product_type or "").lower()
    for key, code in CATEGORY_MAP.items():
        if key in pt:
            return code
    return "equipamiento_accesorios-padel-palas"

def strip_html(html: str) -> str:
    import re
    return re.sub(r"<[^>]+>", "", html or "").strip()

def shopify_product_to_catalog_rows(product: dict) -> list:
    """
    Convierte un producto Shopify al formato de filas CSV de catálogo Sprinter.
    Una fila por variante (talla/color), agrupadas por variant_group_code = handle.
    """
    handle   = product["handle"]
    title    = product["title"]
    vendor   = product.get("vendor", "")
    ptype    = product.get("product_type", "")
    cat      = guess_category(ptype)
    desc     = strip_html(product.get("body_html", ""))
    images   = [img["src"] for img in product.get("images", [])]
    variants = product.get("variants", [])

    rows = []
    for i, v in enumerate(variants):
        ean = (v.get("barcode") or "").strip()
        if not ean:
            continue
        sku  = v.get("sku") or f"{handle}-{v['id']}"
        size = v.get("option1", "") or ""
        # Ignorar "Default Title"
        if size.lower() in ("default title", "default"):
            size = ""

        row = {f: "" for f in PRODUCT_FIELDS}
        row.update({
            "categorias":              cat,
            "sku-de-vendedor":         sku,
            "nombre-del-articulo":     title,
            "nombre-del-articulo-pt":  title,
            "marcas":                  vendor.lower(),
            "genero":                  "unisex",
            "ean":                     ean,
            "descripion-del-producto": desc[:2000],
            "descripion-del-producto-pt": desc[:2000],
            "imagenes-1":              images[0] if len(images) > 0 else "",
            "imagenes-2":              images[1] if len(images) > 1 else "",
            "imagenes-3":              images[2] if len(images) > 2 else "",
            "imagenes-4":              images[3] if len(images) > 3 else "",
            "talla":                   size,
            "variant_group_code":      handle,
            "pais-fabricante":         "España",
            "pais-fabricante-pt":      "Espanha",
            "model":                   handle,
        })
        rows.append(row)
    return rows


def build_product_csv(rows: list) -> str:
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=PRODUCT_FIELDS, delimiter=";",
                            extrasaction="ignore", lineterminator="\n")
    writer.writeheader()
    for row in rows:
        writer.writerow(row)
    return buf.getvalue()


def import_products(rows: list) -> dict:
    """POST /api/products/imports — multipart/form-data con CSV."""
    csv_content = build_product_csv(rows)
    r = requests.post(
        f"{MIRAKL_BASE_URL}/api/products/imports",
        headers={"Authorization": MIRAKL_API_KEY},
        files={"file": ("products.csv", csv_content.encode("iso-8859-1", errors="replace"), "text/csv")},
        data={"import_mode": "NORMAL"},
        timeout=60,
    )
    r.raise_for_status()
    return r.json()


def wait_for_product_import(import_id: str, timeout: int = 180) -> dict:
    deadline = time.time() + timeout
    while time.time() < deadline:
        r = requests.get(
            f"{MIRAKL_BASE_URL}/api/products/imports/{import_id}",
            headers=mirakl_headers(), timeout=20,
        )
        r.raise_for_status()
        data   = r.json()
        status = data.get("import_status", "")
        synced = data.get("integration_details", {}).get("products_successfully_synchronized", 0)
        errors = data.get("integration_details", {}).get("invalid_products", 0)
        print(f"  Product import {import_id}: {status} (ok={synced}, err={errors})")
        if status in ("COMPLETE", "FAILED", "SENT"):
            if status == "SENT":
                print("  ℹ️  Estado SENT = enviado al operador para aprobación (flujo normal en Sprinter).")
            return data
        time.sleep(5)
    return {"import_status": "TIMEOUT"}


def create_and_upload_shopify_product(product_id: str) -> bool:
    """
    Flujo completo:
      1. Crear producto en catálogo Mirakl (P21)
      2. Esperar sincronización
      3. Crear oferta (OF01) con precio/stock de Shopify
    """
    print(f"\n📦 Cargando producto Shopify {product_id}…")
    product  = get_shopify_product(product_id)
    title    = product.get("title", "")
    variants = product.get("variants", [])
    print(f"  → {title} ({len(variants)} variante/s)")

    # ── Paso 1: importar producto al catálogo ─────────────────────────────────
    rows = shopify_product_to_catalog_rows(product)
    if not rows:
        print("  ❌ Sin variantes con EAN — abortando")
        return False

    print(f"\n📋 Paso 1/2 — Importando {len(rows)} fila/s al catálogo Mirakl…")
    try:
        result     = import_products(rows)
        p_import   = result.get("import_id") or result.get("product_import_id", "")
        print(f"  Product import ID: {p_import}")
        if p_import:
            final_p = wait_for_product_import(str(p_import))
            if final_p.get("has_error_report"):
                err_r = requests.get(
                    f"{MIRAKL_BASE_URL}/api/products/imports/{p_import}/error_report",
                    headers=mirakl_headers(), timeout=20,
                )
                print(f"  ⚠️  Errores catálogo:\n{err_r.text[:800]}")
    except Exception as e:
        print(f"  ⚠️  Importación catálogo: {e} — intentando oferta de todas formas…")

    # ── Paso 2: crear oferta ──────────────────────────────────────────────────
    print(f"\n💰 Paso 2/2 — Creando oferta (precio + stock)…")
    offers = []
    for v in variants:
        ean = (v.get("barcode") or "").strip()
        if not ean:
            continue
        shop_sku = v.get("sku") or f"{product['handle']}-{v['id']}"
        price    = float(v.get("price") or 0)
        orig     = float(v.get("compare_at_price") or 0)
        qty      = max(v.get("inventory_quantity", 0) or 0, 0)
        sell_price = orig if orig > price else price
        offers.append({
            "shop-sku":              shop_sku,
            "product-id":           ean,
            "product-id-type":      "EAN",
            "price":                f"{sell_price:.2f}",
            "price-additional-info": "",
            "quantity":             str(qty),
            "state":                OFFER_STATE,
            "leadtime-to-ship":     str(LEADTIME_TO_SHIP),
            "description":          "",
        })
        print(f"  ✓ EAN {ean} | {sell_price:.2f}€ | stock {qty}")

    if offers:
        res       = import_offers(offers)
        import_id = res.get("import_id", "")
        print(f"  Offer import ID: {import_id}")
        if import_id:
            final = wait_for_import(str(import_id))
            print(f"  Estado oferta: {final.get('status')} | "
                  f"ok={final.get('lines_in_success',0)} err={final.get('lines_in_error',0)}")
            if final.get("has_error_report") or final.get("lines_in_error", 0):
                report = get_import_error_report(str(import_id))
                print(f"  ⚠️  Errores oferta:\n{report[:800]}")

    return True


def update_offer_price_stock(product_id: str) -> bool:
    """
    Solo actualiza precio + stock de ofertas ya existentes en Mirakl (sin P21).
    Útil para sync periódico una vez que el producto ya está en catálogo.
    """
    print(f"\n🔄 Actualizando oferta para producto Shopify {product_id}…")
    product  = get_shopify_product(product_id)
    variants = product.get("variants", [])
    print(f"  → {product.get('title','')} ({len(variants)} variante/s)")

    offers = []
    for v in variants:
        ean = (v.get("barcode") or "").strip()
        if not ean:
            continue
        shop_sku = v.get("sku") or f"{product['handle']}-{v['id']}"
        price    = float(v.get("price") or 0)
        orig     = float(v.get("compare_at_price") or 0)
        qty      = max(v.get("inventory_quantity", 0) or 0, 0)
        # Sprinter tiene MAP: no acepta precio por debajo del PVP de catálogo.
        # Usamos compare_at_price como precio de venta si es mayor.
        sell_price = orig if orig > price else price
        offers.append({
            "shop-sku":              shop_sku,
            "product-id":           ean,
            "product-id-type":      "EAN",
            "price":                f"{sell_price:.2f}",
            "price-additional-info": "",
            "quantity":             str(qty),
            "state":                OFFER_STATE,
            "leadtime-to-ship":     str(LEADTIME_TO_SHIP),
            "description":          "",
        })
        print(f"  ✓ EAN {ean} | {sell_price:.2f}€ | stock {qty}")

    if not offers:
        print("  ❌ Sin variantes con EAN")
        return False

    res       = import_offers(offers)
    import_id = res.get("import_id", "")
    print(f"  Offer import ID: {import_id}")
    if import_id:
        final = wait_for_import(str(import_id))
        print(f"  Estado: {final.get('status')} | "
              f"ok={final.get('lines_in_success',0)} err={final.get('lines_in_error',0)}")
        if final.get("has_error_report") or final.get("lines_in_error", 0):
            report = get_import_error_report(str(import_id))
            print(f"  ⚠️  Errores:\n{report[:800]}")
    return True


def shopify_variant_to_offer(product: dict, variant: dict) -> dict:
    """
    Convierte una variante de Shopify en un dict de oferta Mirakl.
    Devuelve None si no tiene EAN (barcode).
    """
    ean = (variant.get("barcode") or "").strip()
    if not ean:
        print(f"  ⚠️  Variante '{variant.get('title')}' sin EAN — omitida")
        return None

    shop_sku   = variant.get("sku") or f"{product['handle']}-{variant['id']}"
    price      = float(variant.get("price") or 0)
    orig_price = float(variant.get("compare_at_price") or 0)
    quantity   = variant.get("inventory_quantity", 0) or 0
    # Sprinter MAP: no acepta precio por debajo del PVP de catálogo
    sell_price = orig_price if orig_price > price else price

    offer = {
        "ean":                  ean,
        "shop-sku":             shop_sku,
        "price":                f"{sell_price:.2f}",
        "price-additional-info": "",
        "quantity":             str(max(quantity, 0)),
        "state":                OFFER_STATE,
        "leadtime-to-ship":     str(LEADTIME_TO_SHIP),
        "description":          "",
        "product-id":           ean,
        "product-id-type":      "EAN",
    }
    return offer


def upload_shopify_product(product_id: str) -> list:
    """
    Carga un producto de Shopify y sube todas sus variantes como ofertas a Mirakl.
    Devuelve la lista de ofertas procesadas.
    """
    print(f"\n📦 Cargando producto Shopify {product_id}…")
    product  = get_shopify_product(product_id)
    variants = product.get("variants", [])
    title    = product.get("title", "")

    print(f"  → {title} ({len(variants)} variante/s)")

    offers = []
    for v in variants:
        offer = shopify_variant_to_offer(product, v)
        if offer:
            offers.append(offer)
            print(f"  ✓ EAN {offer['ean']} | SKU {offer['shop-sku']} | "
                  f"{offer['price']}€ | stock {offer['quantity']}")

    if not offers:
        print("  ❌ Sin ofertas válidas (ninguna variante tiene EAN)")
        return []

    print(f"\n🚀 Importando {len(offers)} oferta/s en Mirakl…")
    result    = import_offers(offers)
    import_id = result.get("import_id") or result.get("id", "")
    print(f"  Import ID: {import_id}")

    if import_id:
        final = wait_for_import(str(import_id))
        errors = final.get("has_error_report", False)
        lines_err = final.get("lines_in_error", 0)
        print(f"  Estado final: {final.get('status')} | ok={final.get('lines_in_success',0)} err={lines_err}")
        if errors or lines_err:
            report = get_import_error_report(str(import_id))
            print(f"\n  ⚠️  Errores en el import:\n{report[:1000]}")

    return offers


# ── CLI ────────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Mirakl Sprinter Client")
    parser.add_argument("--list",         action="store_true", help="Listar ofertas activas")
    parser.add_argument("--upload",       metavar="PRODUCT_ID", help="Crear producto en catálogo + oferta (P21 + OF01)")
    parser.add_argument("--update-offer", metavar="PRODUCT_ID", help="Actualizar precio/stock de oferta existente (solo OF01)")
    parser.add_argument("--status",       metavar="SHOP_SKU",   help="Estado de una oferta")
    parser.add_argument("--import-id",    metavar="ID",         help="Estado de un import")
    args = parser.parse_args()

    if not MIRAKL_API_KEY:
        print("❌ MIRAKL_API_KEY no configurada en .env")
        sys.exit(1)

    if args.list:
        data   = list_offers(max_results=20)
        offers = data.get("offers", [])
        total  = data.get("total_count", 0)
        print(f"\n📋 {total} ofertas en Sprinter (mostrando {len(offers)}):\n")
        for o in offers:
            ean   = next((r["reference"] for r in o.get("product_references", [])
                          if r["reference_type"] == "EAN"), "-")
            print(f"  {'✅' if o['active'] else '❌'} {o.get('product_title','?')[:50]:<50} "
                  f"EAN:{ean}  {o.get('price','?')}€  stock:{o.get('quantity','?')}")

    elif args.upload:
        create_and_upload_shopify_product(args.upload)

    elif args.update_offer:
        update_offer_price_stock(args.update_offer)

    elif args.status:
        offer = get_offer_by_shop_sku(args.status)
        if offer:
            print(json.dumps(offer, indent=2, ensure_ascii=False))
        else:
            print(f"❌ Oferta '{args.status}' no encontrada")

    elif args.import_id:
        status = get_import_status(args.import_id)
        print(json.dumps(status, indent=2, ensure_ascii=False))

    else:
        parser.print_help()


if __name__ == "__main__":
    main()
