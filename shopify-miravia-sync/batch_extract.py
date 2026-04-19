"""
batch_extract.py
Obtiene productos de Shopify, extrae atributos técnicos con Groq/LLM
y muestra los campos listos para el XML de Miravia.
"""

import os, re, json, time, requests
from dotenv import load_dotenv
from gemini_extractor import extract_attributes, attrs_to_miravia_xml_fields, optimize_description

load_dotenv()

SHOPIFY_STORE = "utrsp8-0c.myshopify.com"
SHOPIFY_TOKEN = os.environ["SHOPIFY_TOKEN"]
SHOPIFY_API   = f"https://{SHOPIFY_STORE}/admin/api/2025-01"

HEADERS = {"X-Shopify-Access-Token": SHOPIFY_TOKEN}


def strip_html(html: str) -> str:
    """Elimina etiquetas HTML para pasar texto limpio al LLM."""
    return re.sub(r"<[^>]+>", " ", html or "").strip()


def get_shopify_products(limit: int = 5) -> list:
    r = requests.get(
        f"{SHOPIFY_API}/products.json",
        headers=HEADERS,
        params={"limit": limit, "fields": "id,title,vendor,body_html,variants,images"},
        timeout=30,
    )
    r.raise_for_status()
    return r.json().get("products", [])


def process_products(products: list) -> list:
    results = []
    for i, prod in enumerate(products, 1):
        title     = prod.get("title", "")
        vendor    = prod.get("vendor", "")
        body_html = prod.get("body_html", "") or ""
        variants  = prod.get("variants", [])
        images    = prod.get("images", [])
        variant   = variants[0] if variants else {}

        description_text = strip_html(body_html) or title
        print(f"\n[{i}/{len(products)}] {title}")
        print(f"  Descripción ({len(description_text)} chars): {description_text[:120]}...")

        try:
            raw_attrs      = extract_attributes(description_text)
            miravia_fields = attrs_to_miravia_xml_fields(raw_attrs)

            # Descripción optimizada (segunda llamada al LLM)
            optimized_desc = optimize_description(title, description_text)

            result = {
                "shopify_id":       prod.get("id"),
                "title":            title,
                "vendor":           vendor,
                "ean":              variant.get("barcode") or variant.get("sku", ""),
                "price":            variant.get("price", ""),
                "stock":            variant.get("inventory_quantity", 0),
                "image_url":        images[0]["src"] if images else "",
                "miravia":          miravia_fields,
                "description_html": optimized_desc,
            }
            results.append(result)
            print(f"  ✅  brand={miravia_fields['brand']}  shape={miravia_fields['shape']}"
                  f"  level={miravia_fields['level']}  balance={miravia_fields['balance']}")

        except Exception as e:
            print(f"  ❌  Error extrayendo atributos: {e}")
            results.append({"shopify_id": prod.get("id"), "title": title, "error": str(e)})

        # Respetar rate limit de Groq (30 req/min free tier)
        if i < len(products):
            time.sleep(2)

    return results


if __name__ == "__main__":
    print("📦 Obteniendo productos de Shopify...")
    products = get_shopify_products(limit=5)
    print(f"   {len(products)} productos encontrados.\n")

    results = process_products(products)

    # Guardar resultados en JSON
    out_path = os.path.join(os.path.dirname(__file__), "batch_results.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2, ensure_ascii=False)

    print(f"\n\n{'='*60}")
    print(f"✅  Procesados {len(results)} productos.")
    print(f"💾  Resultados guardados en: {out_path}")
    print(f"{'='*60}\n")

    # Resumen final
    for r in results:
        if "error" in r:
            print(f"  ❌  [{r['shopify_id']}] {r['title']}")
        else:
            m = r["miravia"]
            print(f"  ✅  {r['title']}")
            print(f"       EAN: {r['ean']}  |  Precio: {r['price']} €  |  Stock: {r['stock']}")
            print(f"       Marca: {m['brand']}  |  Forma: {m['shape']}  |  Nivel: {m['level']}")
            print(f"       Material: {m['material']}  |  Núcleo: {m['nucleus']}")
            print(f"       Tecnologías: {m['technology']}")
            print(f"       Atributos extra: {m['additional_attributes']}")
            print(f"\n       ✍️  Descripción optimizada:")
            print(f"       {'-'*56}")
            # Mostrar texto plano eliminando etiquetas HTML para la consola
            desc_plain = re.sub(r"<[^>]+>", "", r.get("description_html", "")).strip()
            desc_plain = re.sub(r"\n+", "\n       ", desc_plain)
            print(f"       {desc_plain}")
            print()
