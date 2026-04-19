"""
app.py — Shopify → Miravia Sync
Flask app con integración Groq/LLM para optimizar descripciones e importar productos.
"""

import os, re, json, time, hashlib, hmac, requests, threading
from flask import Flask, jsonify, request, render_template, Response, stream_with_context
from flask_cors import CORS
from dotenv import load_dotenv
from gemini_extractor import extract_attributes, attrs_to_miravia_xml_fields, optimize_description

load_dotenv()

app = Flask(__name__)
CORS(app)

SHOPIFY_STORE = "utrsp8-0c.myshopify.com"
SHOPIFY_TOKEN = os.environ["SHOPIFY_TOKEN"]
SHOPIFY_API   = f"https://{SHOPIFY_STORE}/admin/api/2025-01"
SHOPIFY_HDR   = {"X-Shopify-Access-Token": SHOPIFY_TOKEN}

MIRAVIA_KEY    = os.environ["MIRAVIA_APP_KEY"]
MIRAVIA_SECRET = os.environ["MIRAVIA_APP_SECRET"]
MIRAVIA_TOKEN  = os.environ["MIRAVIA_ACCESS_TOKEN"]
MIRAVIA_BASE   = "https://api.miravia.es/rest"
CATEGORY_ID    = 62255292

# ── helpers ───────────────────────────────────────────────────────────────────

def strip_html(html: str) -> str:
    return re.sub(r"<[^>]+>", " ", html or "").strip()


def make_numeric_ean(shopify_id, idx: int = 0) -> str:
    """Genera un EAN numérico de 13 dígitos a partir del ID de Shopify + índice."""
    base = f"{abs(int(shopify_id or 0)):010d}{idx:02d}"  # 12 dígitos
    # Dígito de control EAN-13
    digits = [int(d) for d in base]
    check = (10 - (sum(d * (1 if i % 2 == 0 else 3) for i, d in enumerate(digits)) % 10)) % 10
    return base + str(check)


def miravia_call(path: str, params: dict = None, method: str = "GET") -> dict:
    if params is None:
        params = {}
    p = {
        "app_key":      MIRAVIA_KEY,
        "access_token": MIRAVIA_TOKEN,
        "timestamp":    str(int(time.time() * 1000)),
        "sign_method":  "sha256",
        **params,
    }
    base = path + "".join(f"{k}{v}" for k, v in sorted(p.items()))
    p["sign"] = hmac.new(MIRAVIA_SECRET.encode(), base.encode(), hashlib.sha256).hexdigest().upper()
    url = MIRAVIA_BASE + path
    if method == "GET":
        r = requests.get(url, params=p, timeout=30)
    else:
        r = requests.post(url, data=p, timeout=30)
    return r.json()


def build_xml(product: dict) -> str:
    m        = product.get("miravia") or {}
    is_pala  = (product.get("product_type") or "").lower() == "palas de padel"

    # Imágenes (hasta 8)
    images_xml = "\n      ".join(
        f"<Image>{img}</Image>" for img in product.get("images", [product.get("image_url", "")])[:8] if img
    )

    # Atributos comunes a todos los productos
    common_attrs = f"""
      <name><![CDATA[{product['title']}]]></name>
      <description><![CDATA[{product['description_html']}]]></description>
      <brand><![CDATA[{m.get('brand') or product.get('vendor', '')}]]></brand>
      <Does_this_product_have_a_safety_warning>No</Does_this_product_have_a_safety_warning>"""

    # Atributos exclusivos de palas
    pala_attrs = ""
    if is_pala:
        level_map = {"Principiante": "Principiante", "Intermedio": "Intermedio",
                     "Avanzado": "Avanzado", "Profesional": "Profesional"}
        level = level_map.get(m.get("level", ""), "Avanzado")
        shape = m.get("shape", "TEARDROP")

        optional = ""
        if m.get("material"):
            optional += f"<Material><![CDATA[{m['material']}]]></Material>\n      "
        if m.get("nucleus"):
            optional += f"<Nucleus><![CDATA[{m['nucleus']}]]></Nucleus>\n      "
        if m.get("frame"):
            optional += f"<Frame><![CDATA[{m['frame']}]]></Frame>\n      "
        if m.get("balance"):
            optional += f"<Balance><![CDATA[{m['balance']}]]></Balance>\n      "
        if m.get("technology"):
            optional += f"<Technology><![CDATA[{m['technology']}]]></Technology>\n      "

        pala_attrs = f"""
      <Format>{m.get('format', 'Normal')}</Format>
      <shape>{shape}</shape>
      <Level>{level}</Level>
      <Product_certificates>CE certificate</Product_certificates>
      {optional}<Additional_attributes><![CDATA[{m.get('additional_attributes', '')}]]></Additional_attributes>"""

    # Construir SKUs: uno por variante (ropa) o uno único (pala/accesorios sin tallas)
    variants = product.get("variants") or []
    sku_nodes = ""

    if not is_pala and len(variants) > 1:
        slug = re.sub(r"[^a-z0-9]+", "-", product.get("title", "producto").lower()).strip("-")[:30]
        seen_eans = set()
        for idx, v in enumerate(variants):
            raw_ean  = v.get("ean", "") or ""
            # Extraer solo dígitos del barcode (ej: "8445402643059-S" → "8445402643059")
            base_num = re.sub(r"\D", "", raw_ean)
            if not base_num:
                base_num = re.sub(r"\D", "", str(v.get("variant_id") or product.get("id", 0)))
            # Añadir sufijo 1,2,3... al final (S=84454026430591, M=84454026430592, L=84454026430593...)
            ean = f"{base_num}{idx + 1}" if base_num else str(idx + 1)
            seen_eans.add(ean)
            seen_eans.add(ean)
            seller_sku = v.get("sku") or f"{slug}-{idx}"
            size       = v.get("option1") or v.get("option2") or ""
            size_xml   = f"<size><![CDATA[{size}]]></size>\n        " if size else ""
            sku_nodes += f"""
      <Sku>
        <SellerSku>{seller_sku}</SellerSku>
        {size_xml}<ean_code>{ean}</ean_code>
        <quantity>{v.get('stock', 0)}</quantity>
        <price>{v.get('price', product.get('price', '0.00'))}</price>
        <EU_Responsible>Padel el Canaveral SL</EU_Responsible>
        <package_weight>1</package_weight>
        <package_length>10</package_length>
        <package_width>30</package_width>
        <package_height>35</package_height>
      </Sku>"""
    else:
        sku_nodes = f"""
      <Sku>
        <SellerSku>TEMP-{product['ean']}</SellerSku>
        <ean_code>{product['ean']}</ean_code>
        <quantity>{product['stock']}</quantity>
        <price>{product['price']}</price>
        <EU_Responsible>Padel el Canaveral SL</EU_Responsible>
        <package_weight>1</package_weight>
        <package_length>10</package_length>
        <package_width>30</package_width>
        <package_height>35</package_height>
      </Sku>"""

    return f"""<?xml version="1.0" encoding="UTF-8" ?>
<Request>
  <Product>
    <PrimaryCategory>{CATEGORY_ID}</PrimaryCategory>
    <Attributes>{common_attrs}{pala_attrs}
    </Attributes>
    <Skus>{sku_nodes}
    </Skus>
    <Images>
      {images_xml}
    </Images>
  </Product>
</Request>"""


# ── rutas API ─────────────────────────────────────────────────────────────────

@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/products")
def api_products():
    """Devuelve productos de Shopify (paginados)."""
    limit      = int(request.args.get("limit", 20))
    page_info  = request.args.get("page_info", None)
    params = {
        "limit":  limit,
        "fields": "id,title,vendor,body_html,variants,images,status,product_type,tags",
    }
    if page_info:
        params["page_info"] = page_info

    r = requests.get(f"{SHOPIFY_API}/products.json", headers=SHOPIFY_HDR, params=params, timeout=30)
    r.raise_for_status()
    products = r.json().get("products", [])

    # Parsear Link header para paginación
    next_page = None
    link_header = r.headers.get("Link", "")
    for part in link_header.split(","):
        if 'rel="next"' in part:
            match = re.search(r'page_info=([^&>]+)', part)
            if match:
                next_page = match.group(1)

    result = []
    for p in products:
        variants_raw = p.get("variants") or []
        variant      = variants_raw[0] if variants_raw else {}
        images       = [img["src"] for img in p.get("images", [])]

        # Construir lista de variantes con talla/opción para ropa
        all_variants = []
        for v in variants_raw:
            all_variants.append({
                "variant_id": v.get("id", 0),
                "sku":        v.get("sku", ""),
                "ean":        v.get("barcode") or "",
                "price":      v.get("price", "0.00"),
                "stock":      v.get("inventory_quantity", 0),
                "option1":    v.get("option1") or "",
                "option2":    v.get("option2") or "",
                "option3":    v.get("option3") or "",
            })

        result.append({
            "id":           p["id"],
            "title":        p["title"],
            "vendor":       p.get("vendor", ""),
            "status":       p.get("status", "active"),
            "product_type": p.get("product_type", ""),
            "tags":         p.get("tags", ""),
            "ean":          variant.get("barcode") or variant.get("sku", ""),
            "price":        variant.get("price", "0.00"),
            "stock":        variant.get("inventory_quantity", 0),
            "image_url":    images[0] if images else "",
            "images":       images,
            "description":  strip_html(p.get("body_html", "") or ""),
            "body_html":    p.get("body_html", "") or "",
            "variants":     all_variants,
        })

    return jsonify({"products": result, "next_page": next_page})


@app.route("/api/extract", methods=["POST"])
def api_extract():
    """Extrae atributos y genera descripción optimizada para una lista de productos."""
    data     = request.get_json()
    products = data.get("products", [])

    def generate():
        for i, prod in enumerate(products):
            yield f"data: {json.dumps({'type': 'progress', 'index': i, 'title': prod['title']})}\n\n"
            try:
                desc       = prod.get("description") or prod["title"]
                ptype      = (prod.get("product_type") or "").strip()
                is_pala    = ptype.lower() == "palas de padel"

                # Atributos técnicos solo para palas
                if is_pala:
                    raw_attrs      = extract_attributes(desc)
                    miravia_fields = attrs_to_miravia_xml_fields(raw_attrs)
                else:
                    miravia_fields = {"brand": prod.get("vendor", "")}

                # Descripción optimizada para todos, pero prompt adaptado al tipo
                optimized_desc = optimize_description(prod["title"], desc, ptype)

                result = {**prod, "miravia": miravia_fields, "description_html": optimized_desc}
                yield f"data: {json.dumps({'type': 'result', 'index': i, 'product': result})}\n\n"
                time.sleep(1.5)  # rate limit Groq
            except Exception as e:
                yield f"data: {json.dumps({'type': 'error', 'index': i, 'title': prod['title'], 'error': str(e)})}\n\n"

        yield f"data: {json.dumps({'type': 'done'})}\n\n"

    return Response(stream_with_context(generate()), mimetype="text/event-stream",
                    headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@app.route("/api/import", methods=["POST"])
def api_import():
    """Importa un producto (ya procesado) a Miravia."""
    product = request.get_json()

    # Limpiar EAN: quedarse solo con la parte numérica (ej: "8424966050881-S" → "8424966050881")
    raw_ean = product.get("ean", "") or ""
    numeric_ean = raw_ean.split("-")[0].strip() if raw_ean else ""
    if numeric_ean:
        product["ean"] = numeric_ean
    else:
        product["ean"] = str(product.get("id", "000000"))

    # Fallback description: usar body_html de Shopify o el título
    if not product.get("description_html"):
        product["description_html"] = product.get("body_html") or f"<p>{product.get('title', '')}</p>"

    try:
        ts_create  = str(int(time.time() * 1000))
        xml        = build_xml(product)
        resp       = miravia_call("/product/create", {"payload": xml}, method="POST")

        if resp.get("code") != "0":
            msg  = resp.get("message", "Error Miravia")
            code = resp.get("code", "")
            # EAN duplicado → warning, no error bloqueante
            if "eancode already exists" in msg.lower() or "SPU_036" in code:
                detail = (resp.get("detail") or [{}])[0]
                raw_msg = detail.get("message", "")
                import re as _re
                m_sku = _re.search(r"product id:(\d+)", raw_msg)
                existing_id = m_sku.group(1) if m_sku else None
                return jsonify({
                    "ok":          False,
                    "duplicate":   True,
                    "error":       "EAN ya existe en Miravia",
                    "existing_id": existing_id,
                    "raw":         resp,
                })
            return jsonify({"ok": False, "error": msg, "raw": resp})

        data_block       = resp.get("data") or {}
        item_id          = data_block.get("item_id") or data_block.get("ItemId")
        if not item_id:
            return jsonify({"ok": False, "error": "Miravia no devolvió item_id", "raw": resp})
        sku_list         = data_block.get("sku_list") or []
        sku_id           = sku_list[0]["sku_id"] if sku_list else None
        final_seller_sku = f"{item_id}-{ts_create}-0"

        # Renombrar SellerSku al formato estándar
        xml_rename = f"""<?xml version="1.0" encoding="UTF-8" ?>
<Request>
  <Product>
    <ItemId>{item_id}</ItemId>
    <Skus>
      <Sku>
        <SellerSku>TEMP-{product['ean']}</SellerSku>
        <AssociatedSku>{final_seller_sku}</AssociatedSku>
      </Sku>
    </Skus>
  </Product>
</Request>"""
        miravia_call("/product/update", {"payload": xml_rename}, method="POST")

        return jsonify({
            "ok":             True,
            "item_id":        item_id,
            "sku_id":         sku_id,
            "final_sku":      final_seller_sku,
            "miravia_url":    f"https://www.miravia.es/product/{item_id}",
        })

    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


@app.route("/api/miravia-products")
def api_miravia_products():
    """Lista los productos ya publicados en Miravia."""
    offset = int(request.args.get("offset", 0))
    limit  = int(request.args.get("limit", 20))
    resp   = miravia_call("/products/get", {"filter": "all", "limit": str(limit), "offset": str(offset)})
    return jsonify(resp.get("data", {}))


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 7000))
    app.run(host="0.0.0.0", port=port, debug=True)
