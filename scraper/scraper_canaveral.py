#!/usr/bin/env python3
"""
Scraper para padelcanaveral.shop (Shopify JSON API)
Extrae TODAS las palas con todas sus imágenes y genera products.ts

Uso:
    python scraper_canaveral.py                  # scrape + descarga + products.ts
    python scraper_canaveral.py --no-download    # solo JSON + products.ts (sin descargar)
    python scraper_canaveral.py --no-ts          # no sobreescribir products.ts
    python scraper_canaveral.py --pages 5        # limitar páginas (def: todas)
"""

import argparse
import json
import os
import re
import time
import urllib.parse
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Optional

import requests

# ── Config ────────────────────────────────────────────────────────────────────
SHOP_URL      = "https://padelcanaveral.shop"
COLLECTION    = "palas-de-padel"
API_URL       = f"{SHOP_URL}/collections/{COLLECTION}/products.json"
LIMIT         = 250          # máximo permitido por Shopify
REQUEST_DELAY = 0.4
DOWNLOAD_WORKERS = 10

PROJECT_ROOT = Path(__file__).parent.parent
IMAGES_DIR   = PROJECT_ROOT / "public" / "images" / "products" / "palas-2026"
OUTPUT_JSON  = Path(__file__).parent / "scraped_canaveral.json"

HEADERS = {
    "User-Agent": ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                   "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36"),
    "Accept": "application/json",
}

# ── Helpers ───────────────────────────────────────────────────────────────────
def clean_html(text: str) -> str:
    # Eliminar tags HTML
    t = re.sub(r"<[^>]+>", " ", text or "")
    # Colapsar whitespace y newlines
    t = re.sub(r"\s+", " ", t).strip()
    return t

def extract_price(val) -> Optional[float]:
    try:
        return float(val) if val else None
    except (ValueError, TypeError):
        return None

def normalize_image_url(src: str) -> str:
    """Elimina parámetros de tamaño de Shopify y fuerza 1100x1100 si es posible."""
    # Shopify CDN: quitar ?v=... y width= para obtener URL limpia
    url = src.split("?")[0]
    return url

def normalize_filename(slug: str, index: int) -> str:
    return f"{slug}_{index:02d}.jpg"

# ── Scraping ──────────────────────────────────────────────────────────────────
def fetch_all_products(max_pages: Optional[int] = None) -> list:
    products = []
    page = 1

    print(f"🛒  Scrapeando {SHOP_URL}/collections/{COLLECTION}…\n")

    while True:
        if max_pages and page > max_pages:
            break

        print(f"  📄  Página {page}…", end=" ", flush=True)
        params = {"limit": LIMIT, "page": page}

        try:
            r = requests.get(API_URL, params=params, headers=HEADERS, timeout=20)
            r.raise_for_status()
            data = r.json()
        except Exception as e:
            print(f"ERROR: {e}")
            break

        items = data.get("products", [])
        if not items:
            print("sin productos. Fin.")
            break

        parsed = [parse_product(p) for p in items]
        parsed = [p for p in parsed if p]
        products.extend(parsed)
        print(f"{len(parsed)} productos (total: {len(products)})")

        if len(items) < LIMIT:
            break  # última página

        page += 1
        time.sleep(REQUEST_DELAY)

    return products

def parse_product(p: dict) -> Optional[dict]:
    try:
        slug    = p.get("handle", "")
        name    = p.get("title", "").strip()
        vendor  = p.get("vendor", "").strip().upper()
        desc    = clean_html(p.get("body_html", ""))[:300]

        variant = p["variants"][0] if p.get("variants") else {}
        price      = extract_price(variant.get("price"))
        orig_price = extract_price(variant.get("compare_at_price"))
        in_stock   = variant.get("available", True)

        discount = None
        if orig_price and price and orig_price > price:
            discount = round((1 - price / orig_price) * 100)

        images = []
        for img in p.get("images", []):
            src = normalize_image_url(img.get("src", ""))
            if src and src not in images:
                images.append(src)

        return {
            "slug":          slug,
            "name":          name,
            "brand":         vendor,
            "category":      "palas-2026",
            "price":         price,
            "originalPrice": orig_price,
            "discount":      discount,
            "image":         images[0] if images else "",
            "images":        images,
            "inStock":       in_stock,
            "description":   desc or name,
            "productUrl":    f"{SHOP_URL}/collections/{COLLECTION}/products/{slug}",
            "localImage":    "",
            "localImages":   [],
        }
    except Exception as e:
        print(f"\n  ⚠️  parse error: {e}")
        return None

# ── Descarga imágenes ─────────────────────────────────────────────────────────
def download_image(url: str, dest: Path) -> bool:
    if dest.exists():
        return True
    try:
        dest.parent.mkdir(parents=True, exist_ok=True)
        r = requests.get(url, headers={"User-Agent": HEADERS["User-Agent"]},
                         timeout=25, stream=True)
        r.raise_for_status()
        content_type = r.headers.get("Content-Type", "")
        if "image" not in content_type and "octet" not in content_type:
            return False
        with open(dest, "wb") as f:
            for chunk in r.iter_content(8192):
                f.write(chunk)
        return True
    except Exception:
        return False

def download_all(products: list) -> list:
    tasks = []  # (url, dest)
    for p in products:
        p["localImages"] = []
        for idx, img_url in enumerate(p.get("images", []), start=1):
            fname = normalize_filename(p["slug"], idx)
            dest  = IMAGES_DIR / fname
            local = f"/images/products/palas-2026/{fname}"
            p["localImages"].append(local)
            tasks.append((img_url, dest))
        p["localImage"] = p["localImages"][0] if p["localImages"] else ""

    total = len(tasks)
    print(f"\n🖼️   Descargando {total} imágenes ({DOWNLOAD_WORKERS} hilos)…")
    ok = fail = 0
    with ThreadPoolExecutor(max_workers=DOWNLOAD_WORKERS) as ex:
        fts = {ex.submit(download_image, u, d): (u, d) for u, d in tasks}
        for i, ft in enumerate(as_completed(fts), 1):
            if ft.result():
                ok += 1
            else:
                fail += 1
            if i % 50 == 0 or i == total:
                print(f"  [{i}/{total}] ✓{ok}  ✗{fail}")

    print(f"\n✅  {ok} OK, {fail} fallidas")
    return products

# ── Genera products.ts ────────────────────────────────────────────────────────
TS_HEADER = """\
// AUTO-GENERADO por scraper/scraper_canaveral.py
export type Product = {
  id: string; slug: string; name: string; brand: string; category: string
  price: number; originalPrice?: number; discount?: number
  image: string; images: string[]
  badge?: string; isNew?: boolean; isSale?: boolean; inStock?: boolean; description: string
}
export type Category = { slug: string; name: string; description: string; image: string }

export const categories: Category[] = [
  { slug:'palas-2026', name:'Palas 2026',           description:'Lo último de la temporada',         image:'/images/products/palas-2026/category.jpg' },
  { slug:'zapatillas', name:'Zapatillas',            description:'Grip y comodidad en cada paso',      image:'/images/products/zapatillas/category.jpg' },
  { slug:'mochilas',   name:'Mochilas y Paleteros',  description:'Transporta tus palas con estilo',    image:'/images/products/mochilas/category.jpg' },
  { slug:'pelotas',    name:'Pelotas',               description:'Botes de 3 pelotas homologadas',     image:'/images/products/pelotas/category.jpg' },
  { slug:'accesorios', name:'Accesorios',            description:'Todo lo que necesitas en pista',     image:'/images/products/accesorios/category.jpg' },
]

export const products: Product[] = [
"""

def generate_ts(products: list, out: Path) -> None:
    def esc(s: str) -> str:
        # Escapar backslash, comilla simple, y eliminar newlines/tabs
        s = (s or "").replace("\\", "\\\\").replace("'", "\\'")
        s = re.sub(r"[\r\n\t]+", " ", s)
        return s.strip()

    lines = [TS_HEADER]
    for i, p in enumerate(products):
        # Usar imagen local si existe, si no la remota
        local_imgs = p.get("localImages", [])
        if not local_imgs:
            local_imgs = p.get("images", [])

        img = local_imgs[0] if local_imgs else ""
        if img and img.startswith("/"):
            # Verificar que el archivo existe
            local_file = PROJECT_ROOT / img.lstrip("/")
            if not local_file.exists():
                img = p.get("image", "")
        if not img:
            img = f"https://placehold.co/400x400/1a1a2e/fff?text={urllib.parse.quote(p['name'][:20])}"

        imgs_ts = "[" + ", ".join(f"'{esc(x)}'" for x in local_imgs) + "]"

        line  = f"  {{ id:'{i+1}', slug:'{esc(p['slug'])}',"
        line += f" name:'{esc(p['name'])}', brand:'{esc(p['brand'])}', category:'{p['category']}',"
        line += f" price:{p['price'] or 0},"
        if p.get("originalPrice"): line += f" originalPrice:{p['originalPrice']},"
        if p.get("discount"):      line += f" discount:{p['discount']},"
        line += f" image:'{esc(img)}', images:{imgs_ts},"
        line += f" isSale:{str(bool(p.get('discount'))).lower()},"
        line += f" inStock:{str(p.get('inStock', True)).lower()},"
        line += f" description:'{esc(p['description'])}' }},"
        lines.append(line)

    lines += [
        "]",
        "export const getProductsByCategory = (c:string) => products.filter(p=>p.category===c)",
        "export const getProductBySlug = (s:string) => products.find(p=>p.slug===s)",
        "export const getFeaturedProducts = (n=8) => products.filter(p=>p.isSale).slice(0,n)",
        "export const getTopSelling = (n=6) => products.slice(0,n)",
    ]
    out.write_text("\n".join(lines), encoding="utf-8")
    print(f"\n📝  products.ts → {out} ({len(products)} productos)")

# ── Main ──────────────────────────────────────────────────────────────────────
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--no-download", action="store_true", help="No descargar imágenes")
    ap.add_argument("--no-ts",       action="store_true", help="No generar products.ts")
    ap.add_argument("--pages",       type=int, default=None, help="Limitar número de páginas")
    args = ap.parse_args()

    products = fetch_all_products(max_pages=args.pages)

    print(f"\n🔢  Total: {len(products)} palas")
    if not products:
        print("❌  Sin productos."); return

    OUTPUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_JSON.write_text(json.dumps(products, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"💾  JSON → {OUTPUT_JSON}")

    if not args.no_download:
        IMAGES_DIR.mkdir(parents=True, exist_ok=True)
        products = download_all(products)
        OUTPUT_JSON.write_text(json.dumps(products, ensure_ascii=False, indent=2), encoding="utf-8")

    if not args.no_ts:
        ts_out = PROJECT_ROOT / "src" / "data" / "products.ts"
        generate_ts(products, ts_out)
        print("\n🎉  Listo. Reconstruye el contenedor:")
        print("     docker compose up --build -d")

if __name__ == "__main__":
    main()
