#!/usr/bin/env python3
"""
Actualiza las imágenes de UN producto específico en Shopify.

Uso:
    python update_product_images.py \
        --store padelcanaveral.shop \
        --token shpat_XXXX \
        --handle pala-enebe-supra-3k-2024-copia

El script:
1. Busca el producto por handle en Shopify (Admin API)
2. Scrapea las imágenes de PadelPoint para ese handle/nombre
3. Borra las imágenes actuales del producto
4. Sube las nuevas imágenes en orden
"""

import argparse
import re
import sys
import time
from pathlib import Path
from typing import List, Optional

import requests
from bs4 import BeautifulSoup

# ── Helpers API ───────────────────────────────────────────────────────────────
API_VER = "2025-01"
WEB_H   = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"}


def admin_headers(token: str) -> dict:
    return {
        "X-Shopify-Access-Token": token,
        "Content-Type": "application/json",
        "Accept":       "application/json",
    }


def shopify_get(store: str, token: str, path: str) -> dict:
    url = f"https://{store}/admin/api/{API_VER}/{path}"
    r = requests.get(url, headers=admin_headers(token), timeout=20)
    r.raise_for_status()
    return r.json()


def shopify_post(store: str, token: str, path: str, body: dict) -> dict:
    url = f"https://{store}/admin/api/{API_VER}/{path}"
    r = requests.post(url, headers=admin_headers(token), json=body, timeout=30)
    r.raise_for_status()
    return r.json()


def shopify_delete(store: str, token: str, path: str):
    url = f"https://{store}/admin/api/{API_VER}/{path}"
    r = requests.delete(url, headers=admin_headers(token), timeout=15)
    return r.status_code


# ── Buscar producto por handle ────────────────────────────────────────────────
def find_product_by_handle(store: str, token: str, handle: str) -> Optional[dict]:
    data = shopify_get(store, token, f"products.json?handle={handle}&fields=id,title,handle,images")
    prods = data.get("products", [])
    return prods[0] if prods else None


# ── Scraper de imágenes ───────────────────────────────────────────────────────
def scrape_images_from_padelpoint(handle: str, title: str) -> List[str]:
    """
    Intenta encontrar imágenes en tiendapadelpoint.com.
    Prueba primero con el handle, luego busca por título.
    """
    images = []

    # Candidatos de URL directa (handle y variantes comunes)
    candidates = [
        handle,
        handle.replace("-copia", ""),
        handle.replace("_copia", ""),
    ]

    for slug in candidates:
        url = f"https://www.tiendapadelpoint.com/{slug}"
        print(f"  → Probando: {url}")
        try:
            r = requests.get(url, headers=WEB_H, timeout=15)
            if r.status_code != 200:
                continue

            soup = BeautifulSoup(r.text, "lxml")

            # Imágenes del producto: /image/data/ (original) y /image/cache/ (galería alta res)
            # Nombre base del slug (sin -copia)
            slug_clean = re.sub(r'-copia$', '', handle)
            # 1. Imagen principal: /image/data/{slug}.jpg
            raw_data = re.findall(
                r'https://www\.tiendapadelpoint\.com/image/data/[^\s"\'<>\\]+\.(?:jpg|jpeg|png|webp)',
                r.text, re.I
            )
            for u in raw_data:
                u = u.split("?")[0]
                fname = u.lower().split("/")[-1]
                if fname.startswith(slug_clean) and u not in images:
                    images.append(u)

            # 2. Imágenes de galería alta res: /image/cache/data/{slug}-es-N-1100x1100.jpg
            raw_cache = re.findall(
                r'https://www\.tiendapadelpoint\.com/image/cache/data/[^\s"\'<>\\]+-1100x1100\.(?:jpg|jpeg|png)',
                r.text, re.I
            )
            for u in raw_cache:
                u = u.split("?")[0]
                fname = u.lower().split("/")[-1]   # pala-enebe-supra-3k-2024-es-3-1100x1100.jpg
                # Convertir a URL /image/data/ para obtener resolución máxima
                # pala-enebe-supra-3k-2024-es-3-1100x1100.jpg → pala-enebe-supra-3k-2024-es-3.jpg
                base_name = re.sub(r'-\d+x\d+\.', '.', fname)
                if base_name.startswith(slug_clean):
                    original = f"https://www.tiendapadelpoint.com/image/data/{base_name}"
                    if original not in images:
                        images.append(original)

            # data-zoom-image
            for tag in soup.find_all(attrs={"data-zoom-image": True}):
                src = tag["data-zoom-image"]
                if src and src not in images:
                    images.append(src)

            if images:
                print(f"  ✅ {len(images)} imágenes encontradas en {url}")
                break

        except Exception as e:
            print(f"  ⚠️  Error en {url}: {e}")

    # Si no encontramos por URL directa, buscar por nombre
    if not images and title:
        query = title.lower().replace(" ", "+")
        search_url = f"https://www.tiendapadelpoint.com/index.php?route=product/search&search={query}"
        try:
            r = requests.get(search_url, headers=WEB_H, timeout=15)
            soup = BeautifulSoup(r.text, "lxml")
            # Primer resultado
            first_link = next(
                (a["href"] for a in soup.find_all("a", href=True)
                 if a["href"].startswith("https://www.tiendapadelpoint.com/")
                 and "/image/" not in a["href"]
                 and len(a["href"]) > 50),
                None
            )
            if first_link:
                print(f"  → Resultado de búsqueda: {first_link}")
                r2 = requests.get(first_link, headers=WEB_H, timeout=15)
                raw2 = re.findall(
                    r'https://www\.tiendapadelpoint\.com/image/data/[^\s"\'<>\\]+\.(?:jpg|jpeg|png|webp)',
                    r2.text, re.I
                )
                images = list(dict.fromkeys([u.split("?")[0] for u in raw2]))
        except Exception as e:
            print(f"  ⚠️  Error en búsqueda: {e}")

    return images


def verify_images(urls: List[str]) -> List[str]:
    """Verifica que cada URL devuelve una imagen válida."""
    valid = []
    for u in urls:
        try:
            r = requests.head(u, headers=WEB_H, timeout=8, allow_redirects=True)
            if r.status_code == 200 and "image" in r.headers.get("content-type", ""):
                valid.append(u)
            else:
                print(f"    ✗ [{r.status_code}] {u}")
        except Exception:
            print(f"    ✗ [Error] {u}")
    return valid


# ── Main ──────────────────────────────────────────────────────────────────────
def main():
    ap = argparse.ArgumentParser(description="Actualiza imágenes de un producto en Shopify")
    ap.add_argument("--store",  required=True, help="ej: padelcanaveral.shop")
    ap.add_argument("--token",  required=True, help="shpat_XXXX (Admin API token)")
    ap.add_argument("--handle", required=True, help="Handle del producto en Shopify")
    ap.add_argument("--images", nargs="*",     help="URLs de imágenes (opcional, si no se scrapea)")
    ap.add_argument("--dry-run", action="store_true", help="Mostrar sin hacer cambios")
    args = ap.parse_args()

    # Validar formato del token
    if not args.token.startswith("shpat_") and not args.dry_run:
        print(f"⚠️  Aviso: el token no empieza por 'shpat_'. Los tokens Admin deben tener ese prefijo.")
        print(f"   Token actual: {args.token[:12]}...")
        print(f"   Genera uno en: Shopify Admin → Settings → Apps → Develop apps")

    # 1. Buscar producto en Shopify
    print(f"\n🔍  Buscando producto '{args.handle}' en Shopify…")
    if args.dry_run:
        print("  [DRY-RUN] Usando datos de la API pública")
        r = requests.get(
            f"https://{args.store}/products/{args.handle}.json",
            headers=WEB_H, timeout=10
        )
        if r.status_code != 200:
            print(f"  ❌ Producto no encontrado públicamente: {r.status_code}")
            sys.exit(1)
        product = r.json()["product"]
    else:
        try:
            product = find_product_by_handle(args.store, args.token, args.handle)
        except requests.HTTPError as e:
            print(f"  ❌ Error autenticando con Shopify: {e.response.status_code}")
            print(f"     {e.response.text[:200]}")
            sys.exit(1)

    if not product:
        print(f"  ❌ Producto '{args.handle}' no encontrado en la tienda")
        sys.exit(1)

    product_id = str(product["id"])
    title      = product.get("title", args.handle)
    cur_imgs   = product.get("images", [])
    print(f"  ✅ Producto: {title} (id={product_id})")
    print(f"     Imágenes actuales: {len(cur_imgs)}")
    for img in cur_imgs:
        print(f"       [{img['id']}] {img['src'][:80]}")

    # 2. Obtener nuevas imágenes
    if args.images:
        new_images = args.images
        print(f"\n📸  Usando {len(new_images)} imágenes proporcionadas manualmente")
    else:
        print(f"\n🕷️  Buscando imágenes en PadelPoint para '{args.handle}'…")
        new_images = scrape_images_from_padelpoint(args.handle, title)
        if not new_images:
            print("  ❌ No se encontraron imágenes automáticamente.")
            print("     Usa --images URL1 URL2 URL3 para especificarlas manualmente.")
            sys.exit(1)

    # Filtrar solo originales (no thumbnails /cache/ de baja res, mantenemos los ya convertidos)
    new_images = list(dict.fromkeys(new_images))  # eliminar duplicados
    print(f"\n🖼️  Verificando {len(new_images)} imágenes…")
    valid_images = verify_images(new_images)
    print(f"  → {len(valid_images)} imágenes válidas")

    if not valid_images:
        print("  ❌ Ninguna imagen válida. Abortando.")
        sys.exit(1)

    for i, u in enumerate(valid_images, 1):
        print(f"  {i}. {u}")

    if args.dry_run:
        print(f"\n[DRY-RUN] Se subirían {len(valid_images)} imágenes a '{title}' (id={product_id})")
        return

    # 3. Borrar imágenes actuales
    print(f"\n🗑️  Borrando {len(cur_imgs)} imágenes actuales…")
    for img in cur_imgs:
        code = shopify_delete(args.store, args.token,
                              f"products/{product_id}/images/{img['id']}.json")
        print(f"  [{code}] Borrada imagen id={img['id']}")
        time.sleep(0.3)

    # 4. Subir nuevas imágenes
    print(f"\n⬆️  Subiendo {len(valid_images)} imágenes nuevas…")
    uploaded = 0
    for pos, url in enumerate(valid_images, 1):
        try:
            body = {"image": {"src": url, "position": pos, "alt": title}}
            data = shopify_post(args.store, args.token,
                                f"products/{product_id}/images.json", body)
            img_id = data["image"]["id"]
            print(f"  ✅ [{pos}/{len(valid_images)}] Subida → id={img_id}  {url[-50:]}")
            uploaded += 1
            time.sleep(0.4)
        except requests.HTTPError as e:
            print(f"  ❌ Error subiendo {url}: {e.response.status_code} {e.response.text[:150]}")

    print(f"\n{'='*50}")
    print(f"✅  {uploaded}/{len(valid_images)} imágenes subidas a '{title}'")
    print(f"    Ver: https://{args.store}/products/{args.handle}")


if __name__ == "__main__":
    main()
