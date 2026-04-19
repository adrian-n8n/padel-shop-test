#!/usr/bin/env python3
"""
Scraper para tiendapadelpoint.com
Usa la API interna Journal2 SuperFilter (AJAX) para obtener productos reales.

Uso:
    python scraper.py                         # todo: scrape + imágenes + products.ts
    python scraper.py --no-download           # solo scrape + products.ts (sin imágenes)
    python scraper.py --no-ts                 # sin generar products.ts
    python scraper.py --category palas-2026   # solo una categoría
    python scraper.py --pages 3               # máx 3 páginas por categoría
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
from bs4 import BeautifulSoup

# ── Config ────────────────────────────────────────────────────────────────────
BASE_URL  = "https://www.tiendapadelpoint.com"
MODULE_ID = "15"
AJAX_URL  = f"{BASE_URL}/index.php?route=module/journal2_super_filter/products&module_id={MODULE_ID}"

CATEGORIES = {
    "palas-2026": {"path": "60",  "label": "Palas 2026"},
    "zapatillas": {"path": "83",  "label": "Zapatillas"},
    "mochilas":   {"path": "86",  "label": "Mochilas y Paleteros"},
    "pelotas":    {"path": "104", "label": "Pelotas"},
    "accesorios": {"path": "135", "label": "Accesorios"},
}

HEADERS = {
    "User-Agent": ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                   "AppleWebKit/537.36 (KHTML, like Gecko) "
                   "Chrome/123.0.0.0 Safari/537.36"),
    "Accept-Language": "es-ES,es;q=0.9",
    "X-Requested-With": "XMLHttpRequest",
    "Referer": BASE_URL,
}

REQUEST_DELAY    = 0.6
DOWNLOAD_WORKERS = 8
PROJECT_ROOT     = Path(__file__).parent.parent
IMAGES_DIR       = PROJECT_ROOT / "public" / "images" / "products"
OUTPUT_JSON      = Path(__file__).parent / "scraped_products.json"

BRANDS = ["Adidas","Babolat","Bullpadel","Nox","Head","Wilson","Black Crown",
          "Starvie","Vibora","Drop Shot","Siux","Royal Padel","Dunlop","Prince",
          "Joma","Kelme","Munich","Asics","Mizuno","Jhayber","Kswiss"]

# ── Helpers ───────────────────────────────────────────────────────────────────
def slugify(text: str) -> str:
    for src, dst in [("àáâãäå","a"),("èéêë","e"),("ìíîï","i"),("òóôõö","o"),("ùúûü","u"),("ñ","n")]:
        for c in src: text = text.replace(c, dst)
    return re.sub(r"[^a-z0-9]+","-", text.lower().strip()).strip("-")

def extract_price(text: str) -> Optional[float]:
    m = re.search(r"([\d]+[.,][\d]{2})", text.replace("\xa0","").replace(" ",""))
    return float(m.group(1).replace(",",".")) if m else None

def abs_url(src: str) -> str:
    if src.startswith("//"): return "https:"+src
    if src.startswith("/"): return BASE_URL+src
    if src.startswith("http"): return src
    return BASE_URL+"/"+src

def upgrade_res(url: str) -> str:
    return re.sub(r"-(\d+)x(\d+)\.jpg", "-1100x1100.jpg", url)

def extract_brand(name: str) -> str:
    nl = name.lower()
    for b in BRANDS:
        if b.lower() in nl: return b.upper()
    return "UNKNOWN"

def fetch_all_images(product_url: str) -> list:
    """Visita la página del producto y devuelve todas las URLs 1100x1100 del gallery."""
    try:
        r = requests.get(product_url, headers=HEADERS, timeout=15)
        r.raise_for_status()
        soup = BeautifulSoup(r.text, "html.parser")
        urls = []
        for a in soup.select("#product-gallery a[href]"):
            href = a.get("href", "")
            if "image/cache/data" in href and href.endswith(".jpg"):
                # Asegurar resolución máxima
                href = upgrade_res(href)
                if href not in urls:
                    urls.append(href)
        return urls
    except Exception as e:
        print(f"  ⚠️  fetch_all_images: {e}")
        return []

# ── Scraping ──────────────────────────────────────────────────────────────────
def scrape_category(slug: str, path_id: str, max_pages: int) -> list:
    products, seen, page = [], set(), 1
    print(f"\n📦  {CATEGORIES[slug]['label']} (path={path_id})")

    while page <= max_pages:
        print(f"  ��  Página {page}…", end=" ", flush=True)
        payload = {"route":"product/category","path":path_id,
                   "sort":"p.sort_order","order":"ASC","page":str(page),"limit":"24"}
        try:
            r = requests.post(AJAX_URL, data=payload, headers=HEADERS, timeout=15)
            r.raise_for_status()
        except requests.RequestException as e:
            print(f"ERROR: {e}"); break

        soup  = BeautifulSoup(r.text, "html.parser")
        items = soup.select(".instock, .outofstock")
        if not items:
            print("sin productos. Fin."); break

        new = []
        for item in items:
            p = parse_card(item, slug)
            if p and p["slug"] not in seen:
                seen.add(p["slug"]); new.append(p)
        products.extend(new)
        print(f"{len(new)} únicos (total: {len(products)})")

        active = soup.select_one(".pagination li.active")
        has_next = bool(active and active.find_next_sibling("li") and
                        active.find_next_sibling("li").find("a"))
        if not has_next:
            has_next = bool(soup.select_one(".pagination a[rel='next']"))
        if not has_next: break
        page += 1
        time.sleep(REQUEST_DELAY)

    return products

def parse_card(item, category: str) -> Optional[dict]:
    try:
        a = item.select_one(".name a")
        if not a: return None
        name = a.get_text(strip=True)
        url  = a.get("href","")
        if not url.startswith("http"): url = BASE_URL+url
        slug = url.rstrip("/").split("/")[-1] or slugify(name)

        # Imagen
        img_url = ""
        img = item.select_one("img.first-image, img")
        if img:
            for attr in ("src","data-src","data-original"):
                src = img.get(attr,"")
                if src and "no_image" not in src and len(src)>10:
                    img_url = upgrade_res(abs_url(src)); break
        if not img_url:
            link = item.select_one("a.has-second-image, .image a")
            if link:
                m = re.search(r"url\('([^']+)'", link.get("style",""))
                if m: img_url = upgrade_res(abs_url(m.group(1)))
        if not img_url:
            img_url = f"{BASE_URL}/image/cache/data/{slug}-1100x1100.jpg"

        # Precios
        price     = extract_price(item.select_one(".price-new").get_text() if item.select_one(".price-new") else "")
        orig_p    = extract_price(item.select_one(".price-old").get_text() if item.select_one(".price-old") else "")
        discount  = None
        badge     = item.select_one(".label-sale b, .label-sale")
        if badge:
            m = re.search(r"-?(\d+)%", badge.get_text())
            if m: discount = int(m.group(1))
        elif orig_p and price and orig_p > price:
            discount = round((1 - price/orig_p)*100)

        # Stock numérico visible en la card de PadelPoint
        stock_qty = 0
        stock_el = item.select_one(".stock span, .stock")
        if stock_el:
            m_stock = re.search(r"(\d+)", stock_el.get_text())
            if m_stock:
                stock_qty = int(m_stock.group(1))
        # Si no hay número pero está instock, asumir al menos 1
        in_stock = "outofstock" not in item.get("class", [])
        if in_stock and stock_qty == 0:
            stock_qty = 1

        # Obtener todas las imágenes visitando la página del producto
        all_images = fetch_all_images(url)
        if not all_images and img_url:
            all_images = [img_url]
        elif all_images and img_url and img_url not in all_images:
            all_images = [img_url] + all_images
        time.sleep(REQUEST_DELAY)

        return {
            "slug": slug, "name": name, "brand": extract_brand(name),
            "category": category, "price": price, "originalPrice": orig_p,
            "discount": discount,
            "image": all_images[0] if all_images else img_url,
            "images": all_images,
            "inStock": in_stock,
            "stock": stock_qty,
            "productUrl": url, "localImage": "", "localImages": [],
        }
    except Exception as e:
        print(f"\n  ⚠️  {e}"); return None

# ── Descarga imágenes ─────────────────────────────────────────────────────────
def download_image(url: str, dest: Path) -> bool:
    if dest.exists(): return True
    try:
        dest.parent.mkdir(parents=True, exist_ok=True)
        r = requests.get(url, headers={"User-Agent":HEADERS["User-Agent"]}, timeout=20, stream=True)
        r.raise_for_status()
        if "image" not in r.headers.get("Content-Type",""): return False
        with open(dest,"wb") as f:
            for chunk in r.iter_content(8192): f.write(chunk)
        return True
    except Exception: return False

def normalize_image_name(slug: str, index: int) -> str:
    """Nombre normalizado: {slug}_{indice_dos_digitos}.jpg"""
    return f"{slug}_{index:02d}.jpg"

def download_all(products: list) -> list:
    tasks = []  # (url, dest_path, product, field, index)
    for p in products:
        imgs = p.get("images") or ([p["image"]] if p.get("image") else [])
        p["localImages"] = []
        cat = p["category"]
        slug = p["slug"]
        for idx, img_url in enumerate(imgs, start=1):
            fname = normalize_image_name(slug, idx)
            dest  = IMAGES_DIR / cat / fname
            local = f"/images/products/{cat}/{fname}"
            p["localImages"].append(local)
            tasks.append((img_url, dest))
        # Imagen principal = primera
        p["localImage"] = p["localImages"][0] if p["localImages"] else ""

    total = len(tasks)
    print(f"\n🖼️   Descargando {total} imágenes ({DOWNLOAD_WORKERS} hilos)…")
    ok = fail = 0
    with ThreadPoolExecutor(max_workers=DOWNLOAD_WORKERS) as ex:
        fts = {ex.submit(download_image, u, d): (u, d) for u, d in tasks}
        for i, ft in enumerate(as_completed(fts), 1):
            if ft.result(): ok += 1
            else: fail += 1
            if i % 25 == 0 or i == total: print(f"  [{i}/{total}] ✓{ok} ✗{fail}")
    print(f"\n✅  {ok} OK, {fail} fallidas")
    return products

# ── Genera products.ts ────────────────────────────────────────────────────────
TS_TYPES = """\
// AUTO-GENERADO por scraper/scraper.py
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
    def esc(s): return (s or "").replace("\\","\\\\").replace("'","\\'")

    lines = [TS_TYPES]
    for i, p in enumerate(products):
        img = p.get("localImage","")
        if img:
            local = IMAGES_DIR / p["category"] / os.path.basename(img)
            if not local.exists(): img = p.get("image","")
        else:
            img = p.get("image","")
        if not img:
            img = f"https://placehold.co/400x400/1a1a2e/fff?text={urllib.parse.quote(p['name'][:20])}"

        # Array de imágenes locales (o remotas si no se descargaron)
        local_imgs = p.get("localImages", [])
        if not local_imgs:
            all_remote = p.get("images") or ([img] if img else [])
            local_imgs = all_remote
        imgs_ts = "[" + ",".join(f"'{esc(i)}'" for i in local_imgs) + "]"

        line  = f"  {{ id:'{i+1}', slug:'{esc(p['slug'])}',"
        line += f" name:'{esc(p['name'])}', brand:'{esc(p['brand'])}', category:'{p['category']}',"
        line += f" price:{p['price'] or 0},"
        if p.get("originalPrice"): line += f" originalPrice:{p['originalPrice']},"
        if p.get("discount"):      line += f" discount:{p['discount']},"
        line += f" image:'{esc(img)}', images:{imgs_ts},"
        line += f" isSale:{str(bool(p.get('discount'))).lower()},"
        line += f" inStock:{str(p.get('inStock',True)).lower()},"
        line += f" description:'{esc(p['name'])}' }},"
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
    ap.add_argument("--no-download", action="store_true")
    ap.add_argument("--no-ts",       action="store_true")
    ap.add_argument("--category",    default=None)
    ap.add_argument("--pages",       type=int, default=5)
    args = ap.parse_args()

    cats = CATEGORIES
    if args.category:
        if args.category not in CATEGORIES:
            print(f"❌  Categorías: {list(CATEGORIES)}"); return
        cats = {args.category: CATEGORIES[args.category]}

    all_p = []
    for slug, info in cats.items():
        all_p.extend(scrape_category(slug, info["path"], args.pages))

    print(f"\n🔢  Total: {len(all_p)}")
    if not all_p:
        print("❌  Sin productos."); return

    OUTPUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_JSON.write_text(json.dumps(all_p, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"��  JSON → {OUTPUT_JSON}")

    if not args.no_download:
        IMAGES_DIR.mkdir(parents=True, exist_ok=True)
        all_p = download_all(all_p)
        OUTPUT_JSON.write_text(json.dumps(all_p, ensure_ascii=False, indent=2), encoding="utf-8")

    if not args.no_ts:
        generate_ts(all_p, PROJECT_ROOT / "src" / "data" / "products.ts")
        print("\n🎉  Reconstruye el contenedor para ver las imágenes:")
        print("     docker compose up --build -d")

if __name__ == "__main__":
    main()
