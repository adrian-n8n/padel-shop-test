#!/usr/bin/env python3
"""
Dashboard web para scraping y subida de productos a Shopify.
Ejecutar: python dashboard/app.py
Abre: http://localhost:5050
"""

import base64
import json
import os
import queue
import re
import sys
import threading
import time
from pathlib import Path
from typing import Optional

import requests
from flask import Flask, Response, jsonify, request, send_from_directory
from flask_cors import CORS

# ── Rutas ─────────────────────────────────────────────────────────────────────
SCRAPER_DIR  = Path(__file__).parent.parent
PROJECT_ROOT = SCRAPER_DIR.parent
sys.path.insert(0, str(SCRAPER_DIR))

# Importar helpers de scraper y uploader como módulos
import importlib.util, types

def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod  = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod

scraper_mod  = _load("scraper",  SCRAPER_DIR / "scraper.py")
uploader_mod = _load("uploader", SCRAPER_DIR / "shopify_uploader.py")

# ── Flask app ─────────────────────────────────────────────────────────────────
app = Flask(__name__, static_folder="static", static_url_path="/static")
CORS(app)

ENV_FILE     = SCRAPER_DIR / ".env"
SCRAPED_JSON = SCRAPER_DIR / "scraped_products.json"

# Colas para streaming de logs
_scrape_queue:  queue.Queue = queue.Queue()
_upload_queue:  queue.Queue = queue.Queue()
_scrape_running = threading.Event()
_upload_running = threading.Event()

# ── Config ────────────────────────────────────────────────────────────────────
def read_env() -> dict:
    # 1. Valores por defecto
    env = {"SHOPIFY_STORE": "", "SHOPIFY_TOKEN": ""}
    # 2. Leer fichero .env si existe (desarrollo local)
    if ENV_FILE.exists():
        for line in ENV_FILE.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                env[k.strip()] = v.strip().strip("'\"")
    # 3. Variables de entorno del sistema tienen prioridad (Railway / Docker)
    for key in [
        "SHOPIFY_STORE", "SHOPIFY_TOKEN", "SHOPIFY_CLIENT_ID", "SHOPIFY_CLIENT_SECRET",
        "MIRAKL_API_KEY", "MIRAKL_BASE_URL",
        "MIRAVIA_APP_KEY", "MIRAVIA_APP_SECRET", "MIRAVIA_ACCESS_TOKEN", "MIRAVIA_BASE_URL",
    ]:
        if os.environ.get(key):
            env[key] = os.environ[key]
    env["SHOPIFY_STORE"] = env.get("SHOPIFY_STORE", "").rstrip("/")
    return env

def write_env(store: str, token: str):
    """Escribe store y token. En Railway actualiza os.environ; en local, el fichero .env."""
    env = read_env()
    env["SHOPIFY_STORE"] = store
    env["SHOPIFY_TOKEN"] = token
    # Siempre actualizar os.environ para que la sesión actual lo vea
    os.environ["SHOPIFY_STORE"] = store
    os.environ["SHOPIFY_TOKEN"] = token
    # Persistir en fichero solo si existe o estamos en local
    if ENV_FILE.exists() or not os.environ.get("RAILWAY_ENVIRONMENT"):
        lines = []
        seen  = set()
        if ENV_FILE.exists():
            for line in ENV_FILE.read_text().splitlines():
                line = line.strip()
                if not line or line.startswith("#"):
                    lines.append(line)
                    continue
                if "=" in line:
                    k = line.split("=", 1)[0].strip()
                    lines.append(f"{k}={env.get(k, line.split('=',1)[1])}")
                    seen.add(k)
        for k, v in env.items():
            if k not in seen:
                lines.append(f"{k}={v}")
        try:
            ENV_FILE.write_text("\n".join(lines) + "\n")
        except OSError:
            pass  # Sistema de ficheros de solo lectura en Railway

def _apply_env_to_uploader(env: dict):
    """Aplica credenciales del .env al módulo uploader."""
    store = env.get("SHOPIFY_STORE", "").rstrip("/")
    token = env.get("SHOPIFY_TOKEN", "")
    uploader_mod.SHOPIFY_STORE = store
    uploader_mod.SHOPIFY_TOKEN = token
    uploader_mod.BASE_API = f"https://{store}/admin/api/{uploader_mod.API_VERSION}"

def refresh_shopify_token() -> str:
    """
    Renueva el access token usando client_credentials grant.
    Requiere SHOPIFY_CLIENT_ID y SHOPIFY_CLIENT_SECRET en .env.
    Guarda el nuevo token en .env y actualiza el uploader.
    """
    env = read_env()
    client_id     = env.get("SHOPIFY_CLIENT_ID", "")
    client_secret = env.get("SHOPIFY_CLIENT_SECRET", "")
    store         = env.get("SHOPIFY_STORE", "").rstrip("/")

    if not client_id or not client_secret or not store:
        raise RuntimeError("Faltan SHOPIFY_CLIENT_ID o SHOPIFY_CLIENT_SECRET en .env")

    url = f"https://{store}/admin/oauth/access_token"
    payload = {
        "client_id":     client_id,
        "client_secret": client_secret,
        "grant_type":    "client_credentials",
    }
    r = requests.post(url, json=payload, timeout=15)
    if r.status_code != 200:
        raise RuntimeError(f"Token refresh falló {r.status_code}: {r.text[:200]}")

    data  = r.json()
    token = data.get("access_token", "")
    if not token:
        raise RuntimeError(f"Respuesta inesperada: {data}")

    # Guardar nuevo token
    write_env(store, token)
    _apply_env_to_uploader({**env, "SHOPIFY_TOKEN": token})
    return token

def _call_with_autorefresh(fn, *args, **kwargs):
    """
    Llama fn(*args, **kwargs). Si lanza HTTPError 401, renueva el token y reintenta.
    """
    try:
        return fn(*args, **kwargs)
    except Exception as e:
        if "401" in str(e):
            try:
                refresh_shopify_token()
                return fn(*args, **kwargs)
            except Exception as refresh_err:
                raise RuntimeError(f"Auto-refresh falló: {refresh_err}") from e
        raise

@app.route("/api/config", methods=["GET"])
def get_config():
    env = read_env()
    return jsonify({
        "store": env.get("SHOPIFY_STORE", ""),
        "token": env.get("SHOPIFY_TOKEN", ""),
        "configured": bool(env.get("SHOPIFY_STORE") and env.get("SHOPIFY_TOKEN")),
    })

@app.route("/api/config", methods=["POST"])
def save_config():
    data  = request.json or {}
    store = data.get("store", "").strip()
    token = data.get("token", "").strip()
    if not store or not token:
        return jsonify({"error": "store y token son obligatorios"}), 400
    write_env(store, token)
    # Recargar variables en uploader
    os.environ["SHOPIFY_STORE"] = store
    os.environ["SHOPIFY_TOKEN"] = token
    _apply_env_to_uploader({"SHOPIFY_STORE": store, "SHOPIFY_TOKEN": token})
    return jsonify({"ok": True})

# ── Productos por tag de Shopify ──────────────────────────────────────────────
@app.route("/api/shopify/tags")
def get_shopify_tags():
    env = read_env()
    if not env.get("SHOPIFY_STORE") or not env.get("SHOPIFY_TOKEN"):
        return jsonify({"error": "No configurado"}), 400
    try:
        _apply_env_to_uploader(env)
        tags = _call_with_autorefresh(uploader_mod.get_all_tags)
        return jsonify({"tags": tags})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/api/shopify/refresh-token", methods=["POST"])
def api_refresh_token():
    try:
        new_token = refresh_shopify_token()
        return jsonify({"ok": True, "token": new_token[:12] + "…"})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/shopify/products-by-tag")
def get_shopify_products_by_tag():
    tag      = request.args.get("tag", "").strip()
    fetch_all = request.args.get("all", "0") == "1"
    if not tag:
        return jsonify({"error": "Falta parámetro tag"}), 400
    env = read_env()
    if not env.get("SHOPIFY_STORE") or not env.get("SHOPIFY_TOKEN"):
        return jsonify({"error": "No configurado"}), 400
    try:
        _apply_env_to_uploader(env)
        if fetch_all:
            raw = _call_with_autorefresh(uploader_mod.get_products_by_tag, tag)
        else:
            # Primera página solo (máx 250), rápido
            raw = _call_with_autorefresh(uploader_mod.get_products_by_tag_page1, tag)
        products = []
        for p in raw:
            variant = p.get("variants", [{}])[0]
            images  = [img["src"] for img in p.get("images", [])]
            products.append({
                "id":           str(p["id"]),
                "title":        p["title"],
                "handle":       p["handle"],
                "vendor":       p.get("vendor", ""),
                "product_type": p.get("product_type", ""),
                "tags":         p.get("tags", ""),
                "price":        variant.get("price", "0.00"),
                "image_url":    images[0] if images else "",
                "images":       images,
                "description":  p.get("body_html", "") or "",
            })
        return jsonify({"products": products, "total": len(products)})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ── Scraping de imágenes desde PadelPoint para productos Shopify ───────────────
_imgscr_queue:   queue.Queue = queue.Queue()
_imgscr_running  = threading.Event()


def _search_padelpoint(product_name: str) -> list:
    """Busca el producto en PadelPoint por nombre y devuelve sus imágenes."""
    import urllib.parse
    search_url = f"https://www.tiendapadelpoint.com/index.php?route=product/search"
    # Construir query con los tokens más relevantes (marca + modelo, máx 5 palabras)
    tokens = product_name.split()[:5]
    query  = " ".join(tokens)
    try:
        headers = {
            "User-Agent": ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                           "AppleWebKit/537.36 Chrome/123.0 Safari/537.36"),
            "Accept-Language": "es-ES,es;q=0.9",
        }
        r = requests.get(search_url, params={"search": query}, headers=headers, timeout=15)
        r.raise_for_status()
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(r.text, "html.parser")

        # Primer resultado exacto (por nombre)
        name_lower = product_name.lower()
        tokens_lower = [t.lower() for t in tokens if len(t) > 2]
        best_url = None
        best_score = 0

        for item in soup.select(".product-thumb, .instock, .outofstock"):
            a = item.select_one(".name a, h4 a")
            if not a:
                continue
            item_name = a.get_text(strip=True).lower()
            score = sum(1 for t in tokens_lower if t in item_name)
            if score > best_score:
                best_score = score
                best_url = a.get("href", "")

        if not best_url or best_score < 2:
            return []
        if not best_url.startswith("http"):
            best_url = "https://www.tiendapadelpoint.com" + best_url

        return scraper_mod.fetch_all_images(best_url)
    except Exception as e:
        return []


def _run_image_scrape(products: list):
    """Para cada producto Shopify, busca imágenes en PadelPoint y las sube."""
    _imgscr_running.set()
    env = read_env()
    _apply_env_to_uploader(env)

    total = len(products)
    updated = skipped = errors = 0
    try:
        for i, p in enumerate(products, 1):
            _imgscr_queue.put({"type": "progress", "current": i, "total": total, "name": p["title"]})
            images = _search_padelpoint(p["title"])
            if not images:
                _imgscr_queue.put({"type": "log", "msg": f"⚠️ Sin imágenes en PadelPoint: {p['title']}"})
                skipped += 1
                continue

            ok = uploader_mod.update_product_images(p["id"], images)
            if ok:
                updated += 1
                _imgscr_queue.put({"type": "log", "msg": f"✓ {p['title']} → {len(images)} imágenes"})
            else:
                errors += 1
                _imgscr_queue.put({"type": "log", "msg": f"✗ Error subiendo imágenes: {p['title']}"})
            time.sleep(1.0)

        _imgscr_queue.put({"type": "done", "updated": updated, "skipped": skipped, "errors": errors})
    except Exception as e:
        _imgscr_queue.put({"type": "error", "msg": str(e)})
    finally:
        _imgscr_running.clear()


@app.route("/api/scrape/images-from-shopify", methods=["POST"])
def scrape_images_from_shopify():
    if _imgscr_running.is_set():
        return jsonify({"error": "Ya en curso"}), 409
    env = read_env()
    if not env.get("SHOPIFY_STORE") or not env.get("SHOPIFY_TOKEN"):
        return jsonify({"error": "Configura las credenciales primero"}), 400
    data     = request.json or {}
    products = data.get("products", [])
    if not products:
        return jsonify({"error": "Sin productos"}), 400
    while not _imgscr_queue.empty():
        _imgscr_queue.get_nowait()
    t = threading.Thread(target=_run_image_scrape, args=(products,), daemon=True)
    t.start()
    return jsonify({"ok": True})


@app.route("/api/scrape/images-from-shopify/stream")
def scrape_images_stream():
    def generate():
        while True:
            try:
                item = _imgscr_queue.get(timeout=60)
                yield f"data: {json.dumps(item)}\n\n"
                if item["type"] in ("done", "error"):
                    break
            except queue.Empty:
                yield 'data: {"type":"ping"}\n\n'
    return Response(generate(), mimetype="text/event-stream",
                    headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@app.route("/api/scrape/images-from-shopify/status")
def scrape_images_status():
    return jsonify({"running": _imgscr_running.is_set()})


# ── Productos locales (JSON scrapeado) ────────────────────────────────────────
@app.route("/api/products/local", methods=["GET"])
def get_local_products():
    if not SCRAPED_JSON.exists():
        return jsonify([])
    products = json.loads(SCRAPED_JSON.read_text(encoding="utf-8"))
    return jsonify(products)

# ── Productos en Shopify ──────────────────────────────────────────────────────
@app.route("/api/products/shopify", methods=["GET"])
def get_shopify_products():
    env = read_env()
    if not env.get("SHOPIFY_STORE") or not env.get("SHOPIFY_TOKEN"):
        return jsonify({"error": "No configurado"}), 400
    try:
        _apply_env_to_uploader(env)
        existing = _call_with_autorefresh(uploader_mod.get_existing_products_by_handle)
        handles = list(existing.keys())
        # Extraer barcode/EAN del primer variant de cada producto
        barcodes = {}
        for handle, data in existing.items():
            if isinstance(data, dict):
                for v in data.get("variants", []):
                    bc = v.get("barcode") or v.get("sku") or ""
                    if bc:
                        barcodes[handle] = bc
                        break
        return jsonify({"handles": handles, "total": len(handles), "barcodes": barcodes})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/api/products/shopify-all", methods=["GET"])
def get_all_shopify_products():
    """Devuelve todos los productos de Shopify normalizados para la tabla."""
    import time as _t
    env = read_env()
    if not env.get("SHOPIFY_STORE") or not env.get("SHOPIFY_TOKEN"):
        return jsonify({"error": "No configurado"}), 400
    try:
        _apply_env_to_uploader(env)
        store = env["SHOPIFY_STORE"]
        token = env["SHOPIFY_TOKEN"]
        hdrs = {"X-Shopify-Access-Token": token, "Content-Type": "application/json"}
        base = f"https://{store}/admin/api/2024-01"
        products = []
        url = f"{base}/products.json"
        params = {"limit": 250, "fields": "id,title,handle,images,variants,product_type,tags,status"}

        def shopify_get(u, p=None):
            """GET con reintentos ante 429."""
            for attempt in range(6):
                r = requests.get(u, headers=hdrs, params=p, timeout=30)
                if r.status_code == 429:
                    retry_after = float(r.headers.get("Retry-After", 2 ** attempt))
                    _t.sleep(retry_after)
                    continue
                r.raise_for_status()
                return r
            raise Exception("Demasiados reintentos (429) en Shopify")

        while url:
            r = shopify_get(url, params)
            prods = r.json().get("products", [])
            for p in prods:
                variant   = p["variants"][0] if p.get("variants") else {}
                price     = float(variant.get("price", 0) or 0)
                barcode   = variant.get("barcode") or variant.get("sku") or ""
                inv       = variant.get("inventory_quantity", 0) or 0
                img       = p["images"][0]["src"] if p.get("images") else ""
                all_imgs  = [i["src"] for i in p.get("images", [])]
                products.append({
                    "slug":          p["handle"],
                    "shopifyId":     str(p["id"]),
                    "name":          p["title"],
                    "brand":         "",
                    "category":      p.get("product_type", ""),
                    "price":         price if price else None,
                    "originalPrice": None,
                    "discount":      None,
                    "image":         img,
                    "images":        all_imgs,
                    "inStock":       inv > 0,
                    "stock":         inv,
                    "productUrl":    f"https://{store}/products/{p['handle']}",
                    "ean":           barcode,
                    "source":        "shopify",
                })
            link = r.headers.get("Link", "")
            next_url = None
            for part in link.split(","):
                if 'rel="next"' in part:
                    next_url = part.strip().split(";")[0].strip().strip("<>")
                    break
            url = next_url
            params = {}
            # Respetar el bucket de Shopify: ~2 req/s → 0.6s entre páginas
            _t.sleep(0.6)
        return jsonify({"products": products, "total": len(products)})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# ── Scraping con streaming ─────────────────────────────────────────────────────
def _run_scrape(categories: list, pages: int):
    _scrape_running.set()
    import builtins
    orig_print = builtins.print

    def capture_print(*args, **kwargs):
        msg = " ".join(str(a) for a in args)
        _scrape_queue.put({"type": "log", "msg": msg})
        orig_print(*args, **kwargs)

    builtins.print = capture_print
    try:
        cats = scraper_mod.CATEGORIES
        if categories:
            cats = {k: v for k, v in scraper_mod.CATEGORIES.items() if k in categories}

        all_p = []
        for slug, info in cats.items():
            _scrape_queue.put({"type": "log", "msg": f"▶ Scrapeando {info['label']}…"})
            prods = scraper_mod.scrape_category(slug, info["path"], pages)
            all_p.extend(prods)
            _scrape_queue.put({"type": "progress", "category": slug, "count": len(prods)})

        SCRAPED_JSON.parent.mkdir(parents=True, exist_ok=True)
        SCRAPED_JSON.write_text(json.dumps(all_p, ensure_ascii=False, indent=2), encoding="utf-8")
        _scrape_queue.put({"type": "done", "total": len(all_p), "products": all_p})
    except Exception as e:
        _scrape_queue.put({"type": "error", "msg": str(e)})
    finally:
        builtins.print = orig_print
        _scrape_running.clear()

@app.route("/api/scrape", methods=["POST"])
def start_scrape():
    if _scrape_running.is_set():
        return jsonify({"error": "Scraping ya en curso"}), 409
    data       = request.json or {}
    categories = data.get("categories", [])
    pages      = int(data.get("pages", 3))
    while not _scrape_queue.empty():
        _scrape_queue.get_nowait()
    t = threading.Thread(target=_run_scrape, args=(categories, pages), daemon=True)
    t.start()
    return jsonify({"ok": True})

@app.route("/api/scrape/stream")
def scrape_stream():
    def generate():
        while True:
            try:
                item = _scrape_queue.get(timeout=30)
                yield f"data: {json.dumps(item)}\n\n"
                if item["type"] in ("done", "error"):
                    break
            except queue.Empty:
                yield "data: {\"type\":\"ping\"}\n\n"
    return Response(generate(), mimetype="text/event-stream",
                    headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})

@app.route("/api/scrape/status")
def scrape_status():
    return jsonify({"running": _scrape_running.is_set()})

# ── Upload con streaming ───────────────────────────────────────────────────────
def _run_upload(slugs: list, collection: str, update_existing: bool):
    _upload_running.set()
    env = read_env()
    _apply_env_to_uploader(env)

    import builtins
    orig_print = builtins.print
    def capture_print(*args, **kwargs):
        msg = " ".join(str(a) for a in args)
        _upload_queue.put({"type": "log", "msg": msg})
        orig_print(*args, **kwargs)
    builtins.print = capture_print

    created = updated = skipped = errors = 0
    try:
        all_products = json.loads(SCRAPED_JSON.read_text(encoding="utf-8"))
        if slugs:
            all_products = [p for p in all_products if p["slug"] in slugs]

        _upload_queue.put({"type": "log", "msg": f"📦 {len(all_products)} productos a procesar"})

        existing = uploader_mod.get_existing_products_by_handle()
        _upload_queue.put({"type": "log", "msg": f"🔍 {len(existing)} productos ya en Shopify"})

        collection_id = None
        if collection:
            collection_id = uploader_mod.get_or_create_collection(collection)

        total = len(all_products)
        for i, p in enumerate(all_products, 1):
            handle = p.get("slug", "")
            _upload_queue.put({"type": "progress", "current": i, "total": total, "name": p["name"]})

            entry = existing.get(handle)
            if entry:
                pid   = entry["id"] if isinstance(entry, dict) else str(entry)
                evars = entry.get("variants", []) if isinstance(entry, dict) else []
                if update_existing:
                    ok = uploader_mod.update_product(pid, p,
                                                     existing_variants=evars)
                    if ok:
                        updated += 1
                        if collection_id:
                            uploader_mod.add_to_collection(collection_id, pid)
                    else:
                        errors += 1
                else:
                    skipped += 1
                    _upload_queue.put({"type": "log", "msg": f"⏭ Ya existe: {p['name']}"})
            else:
                pid = uploader_mod.create_product(p)
                if pid:
                    created += 1
                    if collection_id:
                        uploader_mod.add_to_collection(collection_id, pid)
                else:
                    errors += 1

            time.sleep(uploader_mod.REQUEST_DELAY)

        _upload_queue.put({
            "type": "done",
            "created": created, "updated": updated,
            "skipped": skipped, "errors": errors,
        })
    except Exception as e:
        _upload_queue.put({"type": "error", "msg": str(e)})
    finally:
        builtins.print = orig_print
        _upload_running.clear()

@app.route("/api/upload", methods=["POST"])
def start_upload():
    if _upload_running.is_set():
        return jsonify({"error": "Upload ya en curso"}), 409
    env = read_env()
    if not env.get("SHOPIFY_STORE") or not env.get("SHOPIFY_TOKEN"):
        return jsonify({"error": "Configura las credenciales de Shopify primero"}), 400
    if not SCRAPED_JSON.exists():
        return jsonify({"error": "Haz un scraping primero"}), 400

    data             = request.json or {}
    slugs            = data.get("slugs", [])         # [] = todos
    collection       = data.get("collection", "")
    update_existing  = bool(data.get("updateExisting", False))

    while not _upload_queue.empty():
        _upload_queue.get_nowait()

    t = threading.Thread(target=_run_upload,
                         args=(slugs, collection, update_existing), daemon=True)
    t.start()
    return jsonify({"ok": True})

@app.route("/api/upload/stream")
def upload_stream():
    def generate():
        while True:
            try:
                item = _upload_queue.get(timeout=60)
                yield f"data: {json.dumps(item)}\n\n"
                if item["type"] in ("done", "error"):
                    break
            except queue.Empty:
                yield "data: {\"type\":\"ping\"}\n\n"
    return Response(generate(), mimetype="text/event-stream",
                    headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})

@app.route("/api/upload/status")
def upload_status():
    return jsonify({"running": _upload_running.is_set()})

# ── Sync rápida precio + stock ────────────────────────────────────────────────
_sync_queue:   queue.Queue = queue.Queue()
_sync_running  = threading.Event()

def _run_sync(slugs: list, dry_run: bool = False):
    """Sincroniza SOLO precio y stock de productos ya existentes en Shopify."""
    _sync_running.set()
    env = read_env()
    _apply_env_to_uploader(env)

    import builtins
    orig_print = builtins.print
    def capture_print(*args, **kwargs):
        msg = " ".join(str(a) for a in args)
        _sync_queue.put({"type": "log", "msg": msg})
        orig_print(*args, **kwargs)
    builtins.print = capture_print

    updated = skipped = errors = not_found = 0
    try:
        all_products = json.loads(SCRAPED_JSON.read_text(encoding="utf-8"))
        if slugs:
            all_products = [p for p in all_products if p["slug"] in slugs]

        _sync_queue.put({"type": "log",
                         "msg": f"🔄 Sincronizando precio/stock de {len(all_products)} productos…"})

        existing = uploader_mod.get_existing_products_by_handle()
        _sync_queue.put({"type": "log",
                         "msg": f"🔍 {len(existing)} productos en Shopify"})

        total = len(all_products)
        for i, p in enumerate(all_products, 1):
            handle = p.get("slug", "")
            _sync_queue.put({"type": "progress", "current": i, "total": total,
                             "name": p["name"]})

            entry = existing.get(handle)
            if not entry:
                not_found += 1
                _sync_queue.put({"type": "log",
                                 "msg": f"⚠️ No existe en Shopify: {p['name']}"})
                continue

            pid   = entry["id"] if isinstance(entry, dict) else str(entry)
            evars = entry.get("variants", []) if isinstance(entry, dict) else []
            variant_id = str(evars[0]["id"]) if evars else None

            if not variant_id:
                # Obtener variante via API
                try:
                    vdata = uploader_mod.api_get(f"products/{pid}/variants.json")
                    vs = vdata.get("variants", [])
                    if vs:
                        variant_id = str(vs[0]["id"])
                except Exception:
                    errors += 1
                    continue

            variant = p.get("variants", [{}])[0] if p.get("variants") else {}
            price      = float(p.get("price") or variant.get("price", 0))
            compare_at = p.get("originalPrice") or variant.get("compare_at_price")
            if compare_at:
                compare_at = float(compare_at)
            in_stock   = p.get("inStock", True)

            ok = uploader_mod.update_price_and_stock(
                pid, variant_id, price, compare_at, in_stock, dry_run=dry_run
            )
            if ok:
                updated += 1
            else:
                errors += 1

            import time as _t; _t.sleep(0.4)

        _sync_queue.put({
            "type": "done",
            "updated": updated, "skipped": skipped,
            "not_found": not_found, "errors": errors,
        })
    except Exception as e:
        _sync_queue.put({"type": "error", "msg": str(e)})
    finally:
        builtins.print = orig_print
        _sync_running.clear()

@app.route("/api/sync", methods=["POST"])
def start_sync():
    if _sync_running.is_set():
        return jsonify({"error": "Sync ya en curso"}), 409
    env = read_env()
    if not env.get("SHOPIFY_STORE") or not env.get("SHOPIFY_TOKEN"):
        return jsonify({"error": "Configura las credenciales de Shopify primero"}), 400
    if not SCRAPED_JSON.exists():
        return jsonify({"error": "Haz un scraping primero"}), 400

    data     = request.json or {}
    slugs    = data.get("slugs", [])
    dry_run  = bool(data.get("dryRun", False))

    while not _sync_queue.empty():
        _sync_queue.get_nowait()

    t = threading.Thread(target=_run_sync, args=(slugs, dry_run), daemon=True)
    t.start()
    return jsonify({"ok": True})

@app.route("/api/sync/stream")
def sync_stream():
    def generate():
        while True:
            try:
                item = _sync_queue.get(timeout=60)
                yield f"data: {json.dumps(item)}\n\n"
                if item["type"] in ("done", "error"):
                    break
            except queue.Empty:
                yield "data: {\"type\":\"ping\"}\n\n"
    return Response(generate(), mimetype="text/event-stream",
                    headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})

@app.route("/api/sync/status")
def sync_status():
    return jsonify({"running": _sync_running.is_set()})

# ── Health check para Railway ─────────────────────────────────────────────────
@app.route("/health")
def health():
    return jsonify({"status": "ok"}), 200

# ── Sirve el frontend ─────────────────────────────────────────────────────────
@app.route("/", defaults={"path": ""})
@app.route("/<path:path>")
def serve_frontend(path):
    static_dir = Path(__file__).parent / "static"
    if path and (static_dir / path).exists():
        return send_from_directory(str(static_dir), path)
    return send_from_directory(str(static_dir), "index.html")

# ── Entry point ───────────────────────────────────────────────────────────────
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5050))
    print(f"🚀  Dashboard iniciado → http://localhost:{port}")
    app.run(host="0.0.0.0", port=port, debug=False, threaded=True)
