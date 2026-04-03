#!/usr/bin/env python3
"""
Descarga imágenes desde tiendapadelpoint.com para los productos de padelcanaveral.shop

Estrategia:
  1. Scraping de las 39 páginas de palas en tiendapadelpoint
  2. Para cada producto (slug de padelpoint), extrae imágenes de la página de producto
  3. Hace matching por slug con los productos de scraped_canaveral.json
  4. Descarga las imágenes a public/images/products/palas-2026/
  5. Regenera products.ts con rutas locales

Uso:
    python fetch_padelpoint_images.py                # todo completo
    python fetch_padelpoint_images.py --no-download  # solo genera JSON de matching
    python fetch_padelpoint_images.py --no-ts        # descarga pero no regenera TS
    python fetch_padelpoint_images.py --limit 50     # limitar productos (prueba)
"""

import argparse
import json
import os
import re
import time
import unicodedata
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
from difflib import SequenceMatcher

import requests
from bs4 import BeautifulSoup

# ── Config ────────────────────────────────────────────────────────────────────
BASE_URL      = "https://www.tiendapadelpoint.com"
PALAS_URL     = f"{BASE_URL}/palas-de-padel"
TOTAL_PAGES   = 39
REQUEST_DELAY = 0.1
DOWNLOAD_WORKERS = 20

PROJECT_ROOT = Path(__file__).parent.parent
IMAGES_DIR   = PROJECT_ROOT / "public" / "images" / "products" / "palas-2026"
OUTPUT_JSON  = Path(__file__).parent / "padelpoint_scraped.json"
CANAVERAL_JSON = Path(__file__).parent / "scraped_canaveral.json"
TS_OUTPUT    = PROJECT_ROOT / "src" / "data" / "products.ts"

HEADERS = {
    "User-Agent": ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                   "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36"),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "es-ES,es;q=0.9",
}

# ── Slug helpers ──────────────────────────────────────────────────────────────

def normalize_slug(s: str) -> str:
    """Normaliza un slug para comparación: lowercase, sin tildes, solo alfanum y guiones."""
    s = s.lower().strip()
    # Eliminar número de referencia final como "-1", "-1-1"
    s = re.sub(r'-\d+(-\d+)?$', '', s)
    # Quitar sufijos de año
    s = re.sub(r'-20\d\d', '', s)
    # Eliminar acentos
    s = ''.join(c for c in unicodedata.normalize('NFD', s) if unicodedata.category(c) != 'Mn')
    # Solo alfanumérico y guiones
    s = re.sub(r'[^a-z0-9-]', '', s)
    s = re.sub(r'-+', '-', s).strip('-')
    return s

def slug_similarity(a: str, b: str) -> float:
    return SequenceMatcher(None, normalize_slug(a), normalize_slug(b)).ratio()

# ── Step 1: Scraping lista de productos de tiendapadelpoint ───────────────────

def fetch_product_list(total_pages: int) -> list[dict]:
    """Obtiene todos los slugs/URLs de productos de tiendapadelpoint."""
    products = []
    seen_slugs = set()

    print(f"📋  Scrapeando lista de productos de tiendapadelpoint ({total_pages} páginas)…")

    for page in range(1, total_pages + 1):
        url = f"{PALAS_URL}?page={page}"
        print(f"  Página {page}/{total_pages}…", end=" ", flush=True)

        try:
            r = requests.get(url, headers=HEADERS, timeout=15)
            soup = BeautifulSoup(r.text, "html.parser")

            count = 0
            # Usar .main-products para filtrar solo los productos del listado
            for a in soup.select(".main-products a[href]"):
                href = a.get("href", "")
                # Solo links directos a productos de palas (no subcategorías)
                if re.search(r'/palas-de-padel/pala-|/palas-de-padel/pack-', href):
                    slug = href.rstrip('/').split('/')[-1]
                    if slug and slug not in seen_slugs:
                        seen_slugs.add(slug)
                        name = a.get_text(strip=True)
                        products.append({
                            "padelpoint_slug": slug,
                            "padelpoint_url": href if href.startswith("http") else f"{BASE_URL}{href}",
                            "padelpoint_name": name or slug,
                        })
                        count += 1

            print(f"{count} nuevos (total: {len(products)})")
        except Exception as e:
            print(f"ERROR: {e}")

        time.sleep(REQUEST_DELAY)

    print(f"\n✅  Total productos encontrados en padelpoint: {len(products)}")
    return products


# ── Step 2: Extraer imágenes de la página de cada producto ────────────────────

def fetch_product_images(product_url: str) -> list[str]:
    """Extrae todas las URLs de imágenes de la página de un producto."""
    try:
        r = requests.get(product_url, headers=HEADERS, timeout=15)
        soup = BeautifulSoup(r.text, "html.parser")

        # Galería principal: #product-gallery a[href]
        images = []
        for a in soup.select("#product-gallery a[href]"):
            href = a["href"]
            if href and "image/cache" in href:
                images.append(href)

        # Si no hay galería, buscar imagen principal
        if not images:
            for img in soup.select(".main-image img, #main-image img"):
                src = img.get("src", "")
                if src and "image/cache" in src:
                    # Intentar obtener versión grande
                    src = re.sub(r'-\d+x\d+\.', '-1100x1100.', src)
                    images.append(src)

        return images
    except Exception as e:
        return []


# ── Step 3: Matching con padelcanaveral ───────────────────────────────────────

def match_products(padelpoint_products: list[dict], canaveral_products: list[dict]) -> list[dict]:
    """Hace matching entre productos de padelpoint y canaveral por slug."""
    print(f"\n🔗  Haciendo matching entre {len(padelpoint_products)} padelpoint y {len(canaveral_products)} canaveral…")

    # Índice de canaveral por slug normalizado
    canaveral_index = {}
    for p in canaveral_products:
        norm = normalize_slug(p["slug"])
        canaveral_index[norm] = p
        # Variantes sin año
        norm_no_year = re.sub(r'-20\d\d', '', norm)
        if norm_no_year not in canaveral_index:
            canaveral_index[norm_no_year] = p

    matched = 0
    unmatched = 0
    result = []

    for pp in padelpoint_products:
        pp_norm = normalize_slug(pp["padelpoint_slug"])

        # Intento 1: coincidencia exacta
        canaveral_match = canaveral_index.get(pp_norm)

        # Intento 2: coincidencia con sufijos eliminados
        if not canaveral_match:
            # Quitar también "pala-" del inicio
            pp_bare = re.sub(r'^pala-', '', pp_norm)
            for k, v in canaveral_index.items():
                k_bare = re.sub(r'^pala-', '', k)
                if pp_bare == k_bare:
                    canaveral_match = v
                    break

        # Intento 3: coincidencia fuzzy por similitud de string
        if not canaveral_match:
            best_score = 0
            best_match = None
            for k, v in canaveral_index.items():
                score = slug_similarity(pp_norm, k)
                if score > best_score:
                    best_score = score
                    best_match = v
            if best_score >= 0.82:
                canaveral_match = best_match

        entry = {**pp}
        if canaveral_match:
            entry["canaveral_slug"] = canaveral_match["slug"]
            entry["canaveral_name"] = canaveral_match["name"]
            matched += 1
        else:
            entry["canaveral_slug"] = None
            unmatched += 1

        result.append(entry)

    print(f"  ✅ Matched: {matched} | ❌ Sin match: {unmatched}")
    return result


# ── Step 4: Descargar imágenes ────────────────────────────────────────────────

def download_image(url: str, dest: Path) -> bool:
    """Descarga una imagen si no existe ya."""
    if dest.exists():
        return True
    try:
        r = requests.get(url, headers=HEADERS, timeout=20, stream=True)
        if r.status_code == 200:
            dest.write_bytes(r.content)
            return True
        return False
    except Exception:
        return False


def _fetch_and_download_product(args: tuple) -> dict:
    """Worker: fetch image URLs from product page + download all images."""
    p, images_dir, force = args
    dest_slug = p["canaveral_slug"]

    # Skip si ya existe al menos la imagen _01 (a menos que force=True)
    first_dest = images_dir / f"{dest_slug}_01.jpg"
    if first_dest.exists() and not force:
        # Collect already-downloaded local images
        local_images = sorted([
            f"/images/products/palas-2026/{f.name}"
            for f in images_dir.glob(f"{dest_slug}_*.jpg")
        ])
        return {**p, "padelpoint_images": [], "local_images": local_images, "_skipped": True}

    # Fetch page
    images = fetch_product_images(p["padelpoint_url"])
    local_images = []
    for idx, img_url in enumerate(images, 1):
        filename = f"{dest_slug}_{idx:02d}.jpg"
        dest = images_dir / filename
        if download_image(img_url, dest):
            local_images.append(f"/images/products/palas-2026/{filename}")

    return {**p, "padelpoint_images": images, "local_images": local_images, "_skipped": False}


def download_all_images(matched_products: list[dict], images_dir: Path, force: bool = False) -> list[dict]:
    """Descarga todas las imágenes en paralelo y añade localImages[] a cada producto."""
    images_dir.mkdir(parents=True, exist_ok=True)

    tasks = [p for p in matched_products if p.get("canaveral_slug")]
    mode = "forzando re-descarga" if force else "skip si ya existe"
    print(f"\n📸  Descargando imágenes de {len(tasks)} productos en paralelo ({DOWNLOAD_WORKERS} workers, {mode})…")

    results_map = {}
    ok = 0
    skipped = 0
    errors = 0
    done = 0

    with ThreadPoolExecutor(max_workers=DOWNLOAD_WORKERS) as executor:
        future_to_p = {executor.submit(_fetch_and_download_product, (p, images_dir, force)): p for p in tasks}
        for future in as_completed(future_to_p):
            done += 1
            try:
                result = future.result()
                slug = result["canaveral_slug"]
                results_map[slug] = result
                if result.get("_skipped"):
                    skipped += 1
                elif result["local_images"]:
                    ok += 1
                else:
                    errors += 1
            except Exception as e:
                errors += 1
            if done % 50 == 0 or done == len(tasks):
                print(f"  [{done:>3}/{len(tasks)}] ✓ OK:{ok} ⏭ Skip:{skipped} ✗ Err:{errors}", flush=True)

    # Actualizar lista de products con resultados
    updated = []
    for p in matched_products:
        slug = p.get("canaveral_slug")
        if slug and slug in results_map:
            updated.append(results_map[slug])
        else:
            updated.append(p)

    print(f"\n  ✅ Nuevas: {ok} | ⏭ Ya existían: {skipped} | ❌ Errores: {errors}")
    return updated


# ── Step 5: Regenerar products.ts ─────────────────────────────────────────────

def esc(s: str) -> str:
    if not s:
        return ""
    s = re.sub(r"[\r\n\t]+", " ", str(s))
    s = s.replace("\\", "\\\\").replace("'", "\\'")
    return s.strip()

def clean_html_text(text: str) -> str:
    t = re.sub(r"<[^>]+>", " ", text or "")
    t = re.sub(r"\s+", " ", t).strip()
    return t

def generate_ts(canaveral_products: list[dict], image_map: dict, out_path: Path):
    """
    Regenera products.ts.
    image_map: { canaveral_slug -> ["/images/products/...01.jpg", ...] }
    """
    print(f"\n📝  Generando {out_path}…")

    lines = [
        "// AUTO-GENERATED — do not edit manually",
        "// Source: padelcanaveral.shop (Shopify API) + tiendapadelpoint.com (images)",
        "",
        "export interface Product {",
        "  id: string;",
        "  slug: string;",
        "  name: string;",
        "  brand: string;",
        "  category: string;",
        "  price: number;",
        "  originalPrice: number | null;",
        "  discount: number | null;",
        "  image: string;",
        "  images: string[];",
        "  inStock: boolean;",
        "  description: string;",
        "  productUrl: string;",
        "  localImage: string;",
        "  localImages: string[];",
        "}",
        "",
        "export const products: Product[] = [",
    ]

    for i, p in enumerate(canaveral_products):
        slug = p.get("slug", "")
        # Obtener imágenes locales desde el image_map
        local_imgs = image_map.get(slug, p.get("localImages", []))
        if not local_imgs:
            # Fallback a imágenes Shopify
            local_imgs = p.get("images", [])

        imgs_str = ", ".join(f"'{esc(x)}'" for x in local_imgs) if local_imgs else ""
        local_img = local_imgs[0] if local_imgs else esc(p.get("image", ""))

        price = p.get("price", 0) or 0
        orig = p.get("originalPrice")
        disc = p.get("discount")
        in_stock = "true" if p.get("inStock", True) else "false"
        desc = esc(clean_html_text(p.get("description", "")))

        lines.append(f"  {{")
        lines.append(f"    id: '{esc(str(i+1))}',")
        lines.append(f"    slug: '{esc(slug)}',")
        lines.append(f"    name: '{esc(p.get('name',''))}',")
        lines.append(f"    brand: '{esc(p.get('brand',''))}',")
        lines.append(f"    category: 'palas',")
        lines.append(f"    price: {price},")
        lines.append(f"    originalPrice: {orig if orig is not None else 'null'},")
        lines.append(f"    discount: {disc if disc is not None else 'null'},")
        lines.append(f"    image: '{local_img}',")
        lines.append(f"    images: [{imgs_str}],")
        lines.append(f"    inStock: {in_stock},")
        lines.append(f"    description: '{desc}',")
        lines.append(f"    productUrl: '{esc(p.get('productUrl',''))}',")
        lines.append(f"    localImage: '{local_img}',")
        lines.append(f"    localImages: [{imgs_str}],")
        lines.append(f"  }},")

    lines.append("];")
    lines.append("")
    lines.append("export function getProductsByCategory(category: string): Product[] {")
    lines.append("  return products.filter(p => p.category === category);")
    lines.append("}")
    lines.append("")
    lines.append("export function getProductBySlug(slug: string): Product | undefined {")
    lines.append("  return products.find(p => p.slug === slug);")
    lines.append("}")
    lines.append("")
    lines.append("export function getFeaturedProducts(n = 8): Product[] {")
    lines.append("  return products.filter(p => p.inStock).slice(0, n);")
    lines.append("}")
    lines.append("")
    lines.append("export function getTopSelling(n = 4): Product[] {")
    lines.append("  return products.filter(p => p.inStock && p.discount && p.discount > 10).slice(0, n);")
    lines.append("}")
    lines.append("")
    lines.append("export interface Category {")
    lines.append("  slug: string;")
    lines.append("  name: string;")
    lines.append("  description: string;")
    lines.append("  image: string;")
    lines.append("}")
    lines.append("")
    lines.append("export const categories: Category[] = [")
    lines.append("  {")
    lines.append("    slug: 'palas',")
    lines.append("    name: 'Palas de Pádel',")
    lines.append("    description: 'Las mejores palas de pádel de todas las marcas',")
    lines.append("    image: '/images/products/palas-2026/adidas-ale-galan-metalbone-3-5-2026_01.jpg',")
    lines.append("  },")
    lines.append("];")
    lines.append("")

    out_path.write_text("\n".join(lines), encoding="utf-8")
    print(f"  ✅  {len(canaveral_products)} productos escritos en {out_path}")


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--no-download", action="store_true", help="Solo matching, sin descargar imágenes")
    parser.add_argument("--no-ts", action="store_true", help="No regenerar products.ts")
    parser.add_argument("--limit", type=int, default=0, help="Limitar número de productos (0=todos)")
    parser.add_argument("--pages", type=int, default=TOTAL_PAGES, help=f"Páginas a scrapear (def:{TOTAL_PAGES})")
    parser.add_argument("--force", action="store_true", help="Forzar re-descarga aunque la imagen ya exista")
    parser.add_argument("--skip-list", action="store_true", help="Usar padelpoint_scraped.json existente")
    args = parser.parse_args()

    # Cargar productos de padelcanaveral (fuente de verdad)
    print(f"📂  Cargando {CANAVERAL_JSON}…")
    with open(CANAVERAL_JSON, encoding="utf-8") as f:
        canaveral_products = json.load(f)
    print(f"  {len(canaveral_products)} productos de padelcanaveral cargados.")

    # Step 1: Obtener lista de productos de padelpoint
    if getattr(args, 'skip_list', False) and OUTPUT_JSON.exists():
        print(f"📂  Usando lista existente: {OUTPUT_JSON}")
        with open(OUTPUT_JSON, encoding="utf-8") as f:
            padelpoint_products = json.load(f)
    else:
        padelpoint_products = fetch_product_list(args.pages)
        with open(OUTPUT_JSON, "w", encoding="utf-8") as f:
            json.dump(padelpoint_products, f, ensure_ascii=False, indent=2)
        print(f"  💾  Guardado en {OUTPUT_JSON}")

    if args.limit:
        padelpoint_products = padelpoint_products[:args.limit]
        print(f"  ⚠️   Limitado a {args.limit} productos")

    # Step 2: Matching
    matched = match_products(padelpoint_products, canaveral_products)

    # Step 3: Descargar imágenes
    image_map = {}
    if not args.no_download:
        matched = download_all_images(matched, IMAGES_DIR, force=args.force)
        # Construir image_map: canaveral_slug -> local_images
        for p in matched:
            if p.get("canaveral_slug") and p.get("local_images"):
                image_map[p["canaveral_slug"]] = p["local_images"]
        print(f"\n  📊  Image map: {len(image_map)} productos con imágenes locales")
    else:
        print("\n⏭️   Descarga omitida (--no-download)")

    # Step 4: Regenerar products.ts
    if not args.no_ts:
        generate_ts(canaveral_products, image_map, TS_OUTPUT)
    else:
        print("\n⏭️   products.ts no regenerado (--no-ts)")

    print("\n🎉  ¡Listo!")


if __name__ == "__main__":
    main()
