#!/usr/bin/env python3
"""
Shopify Product Uploader
========================
Sube (o actualiza) productos scrapeados a una tienda Shopify existente
usando la Admin REST API.

Requiere:
    pip install requests python-dotenv

Configuración (crea scraper/.env):
    SHOPIFY_STORE=tu-tienda.myshopify.com
    SHOPIFY_TOKEN=shpat_xxxxxxxxxxxxxxxxxxxxxxxx

Uso:
    python shopify_uploader.py                          # sube todos los productos
    python shopify_uploader.py --json scraped_canaveral.json
    python shopify_uploader.py --dry-run                # simula sin crear nada
    python shopify_uploader.py --limit 10               # solo los primeros 10
    python shopify_uploader.py --collection "Palas 2026"  # asigna colección
    python shopify_uploader.py --update-existing        # actualiza si ya existe
"""

import argparse
import base64
import json
import os
import time
from pathlib import Path
from typing import Optional

import requests
from dotenv import load_dotenv

# ── Config ────────────────────────────────────────────────────────────────────
load_dotenv(dotenv_path=Path(__file__).parent / ".env")

SHOPIFY_STORE = os.getenv("SHOPIFY_STORE", "")   # ej: mi-tienda.myshopify.com
SHOPIFY_TOKEN = os.getenv("SHOPIFY_TOKEN", "")   # Admin API token

API_VERSION   = "2025-01"
BASE_API      = f"https://{SHOPIFY_STORE}/admin/api/{API_VERSION}"

DEFAULT_JSON  = Path(__file__).parent / "scraped_products.json"
PROJECT_ROOT  = Path(__file__).parent.parent
IMAGES_DIR    = PROJECT_ROOT / "public" / "images" / "products"

REQUEST_DELAY = 0.6   # segundos entre llamadas API (rate limit: 2 req/s en plan Basic)

# ── API helpers ───────────────────────────────────────────────────────────────
def api_headers() -> dict:
    return {
        "X-Shopify-Access-Token": SHOPIFY_TOKEN,
        "Content-Type": "application/json",
        "Accept": "application/json",
    }

def api_get(endpoint: str, params: dict = None) -> dict:
    url = f"{BASE_API}/{endpoint}"
    r = requests.get(url, headers=api_headers(), params=params, timeout=20)
    r.raise_for_status()
    return r.json()

def _paginated_get(url: str, params: dict) -> list:
    """GET paginado con manejo de 429 (rate limit) y header Retry-After."""
    results = []
    while url:
        for attempt in range(5):
            r = requests.get(url, headers=api_headers(), params=params, timeout=30)
            if r.status_code == 429:
                wait = float(r.headers.get("Retry-After", 4))
                time.sleep(wait)
                continue
            r.raise_for_status()
            break
        items = r.json().get("products", [])
        results.extend(items)
        link = r.headers.get("Link", "")
        url = None
        for part in link.split(","):
            if 'rel="next"' in part:
                url = part.strip().split(";")[0].strip().strip("<>")
                break
        params = {}
        if items:
            time.sleep(0.5)
    return results

def api_post(endpoint: str, body: dict) -> dict:
    url = f"{BASE_API}/{endpoint}"
    r = requests.post(url, headers=api_headers(), json=body, timeout=30)
    r.raise_for_status()
    return r.json()

def api_put(endpoint: str, body: dict) -> dict:
    url = f"{BASE_API}/{endpoint}"
    r = requests.put(url, headers=api_headers(), json=body, timeout=30)
    r.raise_for_status()
    return r.json()

# ── Colecciones ───────────────────────────────────────────────────────────────
def get_or_create_collection(title: str) -> Optional[str]:
    """Devuelve el ID de una Custom Collection (la crea si no existe)."""
    data = api_get("custom_collections.json", params={"title": title, "limit": 5})
    cols = data.get("custom_collections", [])
    if cols:
        col_id = str(cols[0]["id"])
        print(f"  📁  Colección existente: '{title}' (id={col_id})")
        return col_id

    body = {"custom_collection": {"title": title, "published": True}}
    data = api_post("custom_collections.json", body)
    col_id = str(data["custom_collection"]["id"])
    print(f"  📁  Colección creada: '{title}' (id={col_id})")
    return col_id

def add_to_collection(collection_id: str, product_id: str) -> None:
    body = {"collect": {"collection_id": int(collection_id), "product_id": int(product_id)}}
    try:
        api_post("collects.json", body)
    except requests.HTTPError as e:
        if "already" in str(e).lower() or e.response.status_code == 422:
            pass  # ya estaba en la colección
        else:
            raise

# ── Productos por tag ─────────────────────────────────────────────────────────
def get_products_by_tag(tag: str) -> list:
    """Devuelve lista de productos Shopify que tienen el tag dado (todas las páginas)."""
    return _paginated_get(
        f"{BASE_API}/products.json",
        {
            "limit": 250,
            "fields": "id,title,handle,tags,images,variants,product_type,vendor,body_html",
            "tag": tag,
        }
    )

def get_products_by_tag_page1(tag: str) -> list:
    """Primera página (máx 250 productos) — rápido para UI."""
    for attempt in range(5):
        r = requests.get(
            f"{BASE_API}/products.json",
            headers=api_headers(),
            params={
                "limit": 250,
                "fields": "id,title,handle,tags,images,variants,product_type,vendor,body_html",
                "tag": tag,
            },
            timeout=30,
        )
        if r.status_code == 429:
            time.sleep(float(r.headers.get("Retry-After", 4)))
            continue
        r.raise_for_status()
        return r.json().get("products", [])
    raise RuntimeError("Rate limit persistente al cargar productos")


def get_all_tags() -> list:
    """Devuelve todos los tags únicos de los productos de la tienda."""
    prods = _paginated_get(
        f"{BASE_API}/products.json",
        {"limit": 250, "fields": "tags"}
    )
    tags = set()
    for p in prods:
        for t in (p.get("tags") or "").split(","):
            t = t.strip()
            if t:
                tags.add(t)
    return sorted(tags)


def update_product_images(product_id: str, image_urls: list) -> bool:
    """Reemplaza las imágenes de un producto Shopify con las URLs dadas."""
    try:
        # Obtener imágenes actuales
        data = api_get(f"products/{product_id}/images.json")
        for img in data.get("images", []):
            try:
                requests.delete(
                    f"{BASE_API}/products/{product_id}/images/{img['id']}.json",
                    headers=api_headers(), timeout=15
                )
                time.sleep(0.2)
            except Exception:
                pass
        # Subir las nuevas
        for pos, url in enumerate(image_urls[:8], start=1):
            body = {"image": {"src": url, "position": pos}}
            api_post(f"products/{product_id}/images.json", body)
            time.sleep(0.3)
        return True
    except Exception as e:
        print(f"  ⚠️  update_product_images: {e}")
        return False


# ── Productos existentes ──────────────────────────────────────────────────────
def get_existing_products_by_handle() -> dict:
    """Retorna un dict {handle: product_id} con TODOS los productos de la tienda (cursor pagination)."""
    existing = {}
    url = f"{BASE_API}/products.json"
    params = {"limit": 250, "fields": "id,handle,variants"}
    while url:
        r = requests.get(url, headers=api_headers(), params=params, timeout=30)
        r.raise_for_status()
        prods = r.json().get("products", [])
        for p in prods:
            existing[p["handle"]] = {
                "id":       str(p["id"]),
                "variants": p.get("variants", []),
            }
        # Cursor pagination via Link header
        link = r.headers.get("Link", "")
        next_url = None
        for part in link.split(","):
            if 'rel="next"' in part:
                next_url = part.strip().split(";")[0].strip().strip("<>")
                break
        url = next_url
        params = {}   # el cursor ya va en la URL
        if prods:
            time.sleep(0.3)
    return existing

def get_product_id(handle: str, existing: dict) -> Optional[str]:
    """Extrae el product_id de la estructura devuelta por get_existing_products_by_handle."""
    entry = existing.get(handle)
    if entry is None:
        return None
    return entry["id"] if isinstance(entry, dict) else str(entry)

# ── Imágenes ──────────────────────────────────────────────────────────────────
def build_image_payload(img_src: str, position: int, alt: str) -> Optional[dict]:
    """
    Construye el payload de imagen para Shopify.
    - Si img_src es una URL http(s): usa 'src' directamente (Shopify la descarga).
    - Si img_src es una ruta local /images/...: lee el archivo y lo sube en base64.
    """
    if img_src.startswith("http"):
        return {"src": img_src, "position": position, "alt": alt}

    # Ruta local (ej: /images/products/palas-2026/babolat-viper_01.jpg)
    local_path = PROJECT_ROOT / img_src.lstrip("/")
    if not local_path.exists():
        return None
    try:
        data = base64.b64encode(local_path.read_bytes()).decode()
        filename = local_path.name
        return {
            "attachment": data,
            "filename": filename,
            "position": position,
            "alt": alt,
        }
    except Exception as e:
        print(f"    ⚠️  Error leyendo imagen local {local_path}: {e}")
        return None

# ── Crear producto ─────────────────────────────────────────────────────────────
def build_product_payload(p: dict) -> dict:
    """Construye el payload completo para crear/actualizar un producto en Shopify."""

    # Determinar imágenes a subir (locales primero, remotas como fallback)
    img_sources = p.get("localImages") or []
    if not img_sources:
        img_sources = p.get("images") or ([p["image"]] if p.get("image") else [])

    images = []
    for idx, src in enumerate(img_sources, start=1):
        payload = build_image_payload(src, idx, p.get("name", ""))
        if payload:
            images.append(payload)

    # Precio con descuento
    price        = str(p.get("price") or 0)
    compare_at   = str(p["originalPrice"]) if p.get("originalPrice") else None

    # Tags desde categoría y marca
    tags_list = [p.get("category", ""), p.get("brand", "")]
    if p.get("discount"):
        tags_list.append("sale")
    tags = ", ".join(t for t in tags_list if t)

    product = {
        "title":        p["name"],
        "handle":       p["slug"],
        "vendor":       p.get("brand", ""),
        "product_type": p.get("category", ""),
        "body_html":    p.get("description", p["name"]),
        "tags":         tags,
        "published":    p.get("inStock", True),
        "variants": [
            {
                "price":            price,
                "compare_at_price": compare_at,
                "inventory_management": "shopify",
                "inventory_quantity":   10 if p.get("inStock", True) else 0,
                "fulfillment_service":  "manual",
                "requires_shipping":    True,
                "taxable":             True,
            }
        ],
        "images": images,
    }

    return {"product": product}

def create_product(p: dict, dry_run: bool = False) -> Optional[str]:
    """Crea un producto nuevo. Devuelve el product_id creado."""
    payload = build_product_payload(p)
    img_count = len(payload["product"]["images"])

    if dry_run:
        print(f"  [DRY-RUN] Crearía: {p['name']} ({img_count} imágenes)")
        return "dry-run-id"

    try:
        data = api_post("products.json", payload)
        product_id = str(data["product"]["id"])
        print(f"  ✅  Creado: {p['name']} → id={product_id} ({img_count} imgs)")
        return product_id
    except requests.HTTPError as e:
        print(f"  ❌  Error creando {p['name']}: {e.response.status_code} {e.response.text[:200]}")
        return None

def update_product(product_id: str, p: dict, dry_run: bool = False,
                   update_images: bool = True, existing_variants: list = None) -> bool:
    """
    Actualiza un producto existente en Shopify:
    - Título, vendor, tipo, descripción, tags, estado publicado
    - Precio, compare_at_price, inventario (en la variante principal)
    - Imágenes (solo si update_images=True)
    """
    payload = build_product_payload(p)
    prod    = payload["product"]
    img_count = len(prod["images"])

    if dry_run:
        price = prod["variants"][0]["price"]
        comp  = prod["variants"][0].get("compare_at_price", "—")
        print(f"  [DRY-RUN] Actualizaría: {p['name']} (id={product_id}) "
              f"precio={price}€ antes={comp} {img_count} imgs")
        return True

    try:
        # ── 1. Actualizar campos del producto ────────────────────────────────
        update_body = {
            "product": {
                "id":           int(product_id),
                "title":        prod["title"],
                "vendor":       prod["vendor"],
                "product_type": prod["product_type"],
                "body_html":    prod["body_html"],
                "tags":         prod["tags"],
                "published":    prod["published"],
            }
        }
        api_put(f"products/{product_id}.json", update_body)
        time.sleep(0.3)

        # ── 2. Actualizar variante principal (precio + stock) ────────────────
        new_variant = prod["variants"][0]
        # Obtener ID de la variante actual si no se pasó
        variant_id = None
        if existing_variants:
            variant_id = str(existing_variants[0]["id"]) if existing_variants else None
        if not variant_id:
            vdata = api_get(f"products/{product_id}/variants.json")
            vs = vdata.get("variants", [])
            if vs:
                variant_id = str(vs[0]["id"])

        if variant_id:
            variant_body = {
                "variant": {
                    "id":                  int(variant_id),
                    "price":               new_variant["price"],
                    "compare_at_price":    new_variant.get("compare_at_price"),
                    "inventory_management": "shopify",
                    "inventory_quantity":  new_variant.get("inventory_quantity", 0),
                    "requires_shipping":   True,
                    "taxable":             True,
                }
            }
            api_put(f"variants/{variant_id}.json", variant_body)
            time.sleep(0.3)

        # ── 3. Actualizar imágenes (opcional) ────────────────────────────────
        if update_images and prod["images"]:
            existing_imgs = api_get(f"products/{product_id}/images.json")
            existing_srcs = {img.get("src", "").split("?")[0]
                             for img in existing_imgs.get("images", [])}

            # Solo reemplazar si las imágenes cambiaron
            new_srcs = set()
            for ip in prod["images"]:
                if "src" in ip:
                    new_srcs.add(ip["src"].split("?")[0])

            images_changed = bool(not new_srcs.issubset(existing_srcs))
            if images_changed or any("attachment" in ip for ip in prod["images"]):
                # Borrar imágenes existentes
                for img in existing_imgs.get("images", []):
                    requests.delete(
                        f"{BASE_API}/products/{product_id}/images/{img['id']}.json",
                        headers=api_headers(), timeout=10
                    )
                    time.sleep(0.15)
                # Subir nuevas imágenes
                for img_payload in prod["images"]:
                    try:
                        api_post(f"products/{product_id}/images.json", {"image": img_payload})
                        time.sleep(0.25)
                    except Exception as e:
                        print(f"    ⚠️  Error subiendo imagen: {e}")

        print(f"  🔄  Actualizado: {p['name']} (id={product_id}, "
              f"precio={new_variant['price']}€, {img_count} imgs)")
        return True
    except requests.HTTPError as e:
        print(f"  ❌  Error actualizando {p['name']}: "
              f"{e.response.status_code} {e.response.text[:200]}")
        return False


def update_price_and_stock(product_id: str, variant_id: str,
                           price: float, compare_at: Optional[float],
                           in_stock: bool, dry_run: bool = False) -> bool:
    """
    Actualización rápida: solo precio y stock de una variante.
    Ideal para sincronización periódica sin tocar imágenes ni descripción.
    """
    if dry_run:
        print(f"  [DRY-RUN] precio={price}€ antes={compare_at} stock={'✓' if in_stock else '✗'}")
        return True
    try:
        body = {
            "variant": {
                "id":               int(variant_id),
                "price":            str(price),
                "compare_at_price": str(compare_at) if compare_at else None,
                "inventory_quantity": 10 if in_stock else 0,
            }
        }
        api_put(f"variants/{variant_id}.json", body)
        return True
    except requests.HTTPError as e:
        print(f"  ❌  Error precio/stock variant={variant_id}: "
              f"{e.response.status_code} {e.response.text[:150]}")
        return False

# ── Main ──────────────────────────────────────────────────────────────────────
def main():
    ap = argparse.ArgumentParser(description="Sube productos scrapeados a Shopify")
    ap.add_argument("--json",             default=str(DEFAULT_JSON),
                    help="Ruta al JSON de productos (default: scraped_products.json)")
    ap.add_argument("--collection",       default=None,
                    help="Nombre de la colección donde añadir los productos")
    ap.add_argument("--limit",            type=int, default=None,
                    help="Procesar solo los primeros N productos")
    ap.add_argument("--dry-run",          action="store_true",
                    help="Simula la subida sin crear nada en Shopify")
    ap.add_argument("--update-existing",  action="store_true",
                    help="Actualiza productos que ya existen (por handle/slug)")
    ap.add_argument("--skip-images",      action="store_true",
                    help="No subir imágenes (más rápido para pruebas)")
    args = ap.parse_args()

    # Validar credenciales
    if not args.dry_run:
        if not SHOPIFY_STORE or not SHOPIFY_TOKEN:
            print("❌  Faltan credenciales. Crea scraper/.env con:")
            print("    SHOPIFY_STORE=tu-tienda.myshopify.com")
            print("    SHOPIFY_TOKEN=shpat_xxxxxxxxxx")
            return

    # Cargar productos
    json_path = Path(args.json)
    if not json_path.exists():
        print(f"❌  No se encuentra: {json_path}")
        return

    products = json.loads(json_path.read_text(encoding="utf-8"))
    print(f"📦  {len(products)} productos cargados desde {json_path.name}")

    if args.limit:
        products = products[: args.limit]
        print(f"🔢  Limitado a {args.limit} productos")

    if args.skip_images:
        for p in products:
            p["localImages"] = []
            p["images"] = []

    # Obtener colección (opcional)
    collection_id = None
    if args.collection and not args.dry_run:
        print(f"\n🗂️   Buscando/creando colección '{args.collection}'…")
        collection_id = get_or_create_collection(args.collection)
        time.sleep(REQUEST_DELAY)

    # Obtener productos existentes para detectar duplicados
    existing = {}
    if not args.dry_run:
        print("\n🔍  Comprobando productos existentes en Shopify…")
        existing = get_existing_products_by_handle()
        print(f"    → {len(existing)} productos ya en la tienda")

    # Procesar
    print(f"\n🚀  Procesando {len(products)} productos…\n")
    created = updated = skipped = errors = 0

    for i, p in enumerate(products, 1):
        handle = p.get("slug", "")
        prefix = f"[{i:>3}/{len(products)}]"

        if handle in existing:
            entry = existing[handle]
            pid   = entry["id"] if isinstance(entry, dict) else str(entry)
            evars = entry.get("variants", []) if isinstance(entry, dict) else []
            if args.update_existing:
                success = update_product(pid, p, dry_run=args.dry_run,
                                         existing_variants=evars)
                if success:
                    updated += 1
                    if collection_id and not args.dry_run:
                        add_to_collection(collection_id, pid)
                else:
                    errors += 1
            else:
                print(f"  {prefix} ⏭️  Ya existe: {p['name']} (handle={handle})")
                skipped += 1
        else:
            product_id = create_product(p, dry_run=args.dry_run)
            if product_id and product_id != "dry-run-id":
                created += 1
                if collection_id:
                    add_to_collection(collection_id, product_id)
                    time.sleep(0.3)
            elif product_id == "dry-run-id":
                created += 1
            else:
                errors += 1

        if not args.dry_run:
            time.sleep(REQUEST_DELAY)

    # Resumen
    print(f"""
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
✅  Creados:       {created}
🔄  Actualizados:  {updated}
⏭️   Omitidos:      {skipped}
❌  Errores:       {errors}
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
""")

if __name__ == "__main__":
    main()
