"""
gemini_extractor.py
Extrae atributos técnicos de palas de pádel a partir de su descripción
usando la API de Gemini. Devuelve un dict listo para inyectar en el XML de Miravia.
"""

import os, json, re
from groq import Groq
from dotenv import load_dotenv

load_dotenv()

client = Groq(api_key=os.environ["GROQ_API_KEY"])

PROMPT_TEMPLATE = """
Eres un experto en palas de pádel. A partir del siguiente texto de descripción de producto,
extrae los atributos técnicos y devuelve ÚNICAMENTE un JSON válido con estas claves exactas
(usa null si no se puede determinar el valor):

{{
  "brand": "nombre de la marca (ej: Nox, Starvie, Adidas...)",
  "shape": "forma de la pala en inglés: ROUND | TEARDROP | DIAMOND",
  "level": "nivel del jugador en inglés: Beginner | Intermediate | Advanced | Professional",
  "material": "material de la cara (ej: Carbon 18K Alum, Fibra de vidrio...)",
  "nucleus": "material del núcleo (ej: EVA Soft, EVA Ultra Speed Soft, Foam...)",
  "frame": "material del marco (ej: Carbon Frame, Fibra de carbono...)",
  "balance": "bajo | medio | alto | medio-alto",
  "technology": "tecnologías destacadas separadas por coma",
  "format": "Normal",
  "product_certificates": "Certificado CE",
  "additional_attributes": "clave:valor;clave:valor — atributos extra relevantes (peso, grip, sistema de balance, superficie...)"
}}

Descripción del producto:
{description}

Responde SOLO con el JSON, sin explicaciones ni bloques de código markdown.
"""


def extract_attributes(description: str) -> dict:
    """
    Llama a Gemini y devuelve un dict con los atributos del producto.
    """
    prompt = PROMPT_TEMPLATE.format(description=description)

    response = client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=[{"role": "user", "content": prompt}],
        temperature=0.1,
    )
    raw = response.choices[0].message.content.strip()

    # Eliminar bloque de código markdown si Gemini lo incluye igualmente
    raw = re.sub(r"^```(?:json)?\s*", "", raw)
    raw = re.sub(r"\s*```$", "", raw)

    try:
        attrs = json.loads(raw)
    except json.JSONDecodeError as e:
        raise ValueError(f"Gemini no devolvió JSON válido:\n{raw}") from e

    return attrs


def attrs_to_miravia_xml_fields(attrs: dict) -> dict:
    """
    Convierte el dict de atributos al formato esperado por el XML de Miravia.
    Devuelve un dict con las claves del bloque <Attributes>.
    """
    shape_map = {
        "round": "ROUND",
        "teardrop": "TEARDROP",
        "diamond": "DIAMOND",
    }
    level_map = {
        "beginner": "Principiante",
        "intermediate": "Intermedio",
        "advanced": "Avanzado",
        "professional": "Profesional",
    }

    return {
        "brand":               attrs.get("brand") or "",
        "shape":               shape_map.get((attrs.get("shape") or "").lower(), attrs.get("shape") or "TEARDROP"),
        "level":               level_map.get((attrs.get("level") or "").lower(), attrs.get("level") or "Avanzado"),
        "material":            attrs.get("material") or "",
        "nucleus":             attrs.get("nucleus") or "",
        "frame":               attrs.get("frame") or "",
        "balance":             attrs.get("balance") or "",
        "technology":          attrs.get("technology") or "",
        "format":              attrs.get("format") or "Normal",
        "product_certificates": "CE certificate",
        "additional_attributes": attrs.get("additional_attributes") or "",
    }


OPTIMIZE_PROMPT_PALA = """
Eres un experto en copywriting para marketplaces de pádel en España (Miravia).
A partir del siguiente título y descripción original, genera una descripción de producto
optimizada en HTML para Miravia. Debe:
- Estar en español, tono dinámico y orientado a la venta
- Empezar con un párrafo gancho de 2-3 frases que destaque el beneficio principal
- Incluir una sección <strong>Características técnicas</strong> con lista <ul><li>
- Incluir una sección <strong>¿Para quién es esta pala?</strong> de 1-2 frases
- Terminar con una llamada a la acción corta
- NO incluir precios ni mencionar otras tiendas
- Longitud: entre 200 y 350 palabras
- Devuelve SOLO el HTML, sin explicaciones ni bloques markdown

Título: {title}
Descripción original:
{description}
"""

OPTIMIZE_PROMPT_GENERIC = """
Eres un experto en copywriting para marketplaces deportivos en España (Miravia).
A partir del siguiente título y descripción original, genera una descripción de producto
optimizada en HTML para Miravia. Debe:
- Estar en español, tono dinámico y orientado a la venta
- Empezar con un párrafo gancho de 2-3 frases que destaque el beneficio principal del producto
- Incluir una sección <strong>Características principales</strong> con lista <ul><li>
- Incluir una sección <strong>¿Para quién está pensado?</strong> de 1-2 frases según el tipo de producto (ropa, calzado, accesorio, etc.)
- Terminar con una llamada a la acción corta
- NO incluir precios ni mencionar otras tiendas
- NO asumir que el producto es una pala de pádel
- Longitud: entre 200 y 350 palabras
- Devuelve SOLO el HTML, sin explicaciones ni bloques markdown

Título: {title}
Descripción original:
{description}
"""


def optimize_description(title: str, description: str, product_type: str = "") -> str:
    """
    Genera una descripción HTML optimizada para Miravia usando Groq.
    Usa prompt específico para palas y genérico para el resto.
    """
    is_pala = product_type.lower() == "palas de padel"
    template = OPTIMIZE_PROMPT_PALA if is_pala else OPTIMIZE_PROMPT_GENERIC
    prompt = template.format(title=title, description=description)
    response = client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=[{"role": "user", "content": prompt}],
        temperature=0.4,
    )
    raw = response.choices[0].message.content.strip()
    raw = re.sub(r"^```(?:html)?\s*", "", raw)
    raw = re.sub(r"\s*```$", "", raw)
    return raw


# ── Demo rápido ────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    description = """
    La Pala Nox AT10 Genius 18K Alum 2026 By Agustin Tapia ofrece un molde renovado
    que mejora cada golpe en la pista. Incorpora el Weight Balance System para ajustar
    el balance según tu estilo de juego y ofrecer una experiencia totalmente personalizable.
    Además, la Chromic Paint y la superficie Dual Spin maximizan los efectos y el control
    sin comprometer la durabilidad, ideal para jugadores avanzados que buscan potencia y
    precisión en cada remate.

    Características clave
    Peso: 360–375 g
    Balance ajustable: Weight Balance System (incluye piezas de 2 g y 4 g)
    Superficie: Dual Spin (textura 3D + acabado arenado) para más efectos y control
    CARA y MARCO: Carbono 18K Alum y Carbon Frame con MLD Black EVA
    Forma y Empuñadura: Forma Gota/Lágrima y Oversize Grip
    Chromic Paint, EOS TUNNEL y DCS para diseño, aerodinámica y durabilidad
    This product is offered by Padel Cañaveral.
    """

    print("🔍 Extrayendo atributos con Gemini...\n")
    raw_attrs = extract_attributes(description)
    print("📦 Atributos extraídos (raw):")
    print(json.dumps(raw_attrs, indent=2, ensure_ascii=False))

    miravia_fields = attrs_to_miravia_xml_fields(raw_attrs)
    print("\n📋 Campos para Miravia XML:")
    print(json.dumps(miravia_fields, indent=2, ensure_ascii=False))

    print("\n✍️  Descripción optimizada para Miravia:")
    print("-" * 60)
    optimized = optimize_description("Nox AT10 Genius 18K Alum 2026 By Agustin Tapia", description)
    print(optimized)
