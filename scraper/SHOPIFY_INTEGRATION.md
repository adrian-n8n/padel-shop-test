# Integración Scraper → Shopify Admin API

Documentación técnica del sistema de scraping y sincronización de productos con Shopify para la tienda de pádel.

---

## Índice

1. [Arquitectura general](#1-arquitectura-general)
2. [Estructura de ficheros](#2-estructura-de-ficheros)
3. [Configuración inicial](#3-configuración-inicial)
4. [Cómo obtener el token de Shopify](#4-cómo-obtener-el-token-de-shopify)
5. [Flujo completo paso a paso](#5-flujo-completo-paso-a-paso)
6. [Módulo scraper.py](#6-módulo-scraperpy)
7. [Módulo shopify_uploader.py](#7-módulo-shopify_uploaderpy)
8. [Dashboard web](#8-dashboard-web)
9. [API REST del dashboard](#9-api-rest-del-dashboard)
10. [Modelo de datos del producto](#10-modelo-de-datos-del-producto)
11. [Mapeo de campos a Shopify](#11-mapeo-de-campos-a-shopify)
12. [Gestión de imágenes](#12-gestión-de-imágenes)
13. [Detección de duplicados](#13-detección-de-duplicados)
14. [Rate limiting y throttling](#14-rate-limiting-y-throttling)
15. [Uso por línea de comandos](#15-uso-por-línea-de-comandos)
16. [Casos de uso frecuentes](#16-casos-de-uso-frecuentes)
17. [Errores comunes y soluciones](#17-errores-comunes-y-soluciones)

---

## 1. Arquitectura general

```
┌─────────────────────────┐
│  tiendapadelpoint.com   │  ← Fuente de datos (HTML / AJAX)
│  padelcanaveral.shop    │  ← Fuente alternativa (Shopify JSON API)
└────────────┬────────────┘
             │ HTTP scraping
             ▼
┌─────────────────────────┐
│      scraper.py         │  Extrae: nombre, precio, marca,
│  scraper_canaveral.py   │  imágenes, stock, URL producto
└────────────┬────────────┘
             │ scraped_products.json
             ▼
┌─────────────────────────┐
│  shopify_uploader.py    │  Crea / actualiza productos
│  (CLI o vía dashboard)  │  via Shopify Admin REST API
└────────────┬────────────┘
             │ HTTPS Admin API
             ▼
┌─────────────────────────┐
│   Shopify Store         │  Productos, imágenes, colecciones,
│   (tu-tienda.myshopify) │  variantes e inventario
└─────────────────────────┘

      ┌──────────────────────────────┐
      │   dashboard/app.py (Flask)   │  ← Interfaz web visual
      │   http://localhost:5050      │     para todo lo anterior
      └──────────────────────────────┘
```

El sistema tiene **tres modos de uso**:

| Modo | Cuándo usarlo |
|------|---------------|
| **CLI directo** | Automatización, cron jobs, scripts CI/CD |
| **Dashboard web** | Uso manual con revisión visual antes de subir |
| **Integración Python** | Importar los módulos en otros scripts propios |

---

## 2. Estructura de ficheros

```
scraper/
├── scraper.py                  # Scraper de tiendapadelpoint.com
├── scraper_canaveral.py        # Scraper de padelcanaveral.shop
├── shopify_uploader.py         # Subida a Shopify Admin API
├── run_dashboard.sh            # Script de arranque del dashboard
├── requirements.txt            # Dependencias Python
├── .env                        # Credenciales (NO subir a git)
├── .env.example                # Plantilla de credenciales
├── scraped_products.json       # Caché de productos scrapeados
├── scraped_canaveral.json      # Caché de productos de Canaveral
│
├── dashboard/
│   ├── app.py                  # Servidor Flask (backend API)
│   └── static/
│       ├── index.html          # Interfaz web
│       ├── style.css           # Estilos dark mode
│       └── app.js              # Lógica frontend
│
└── SHOPIFY_INTEGRATION.md      # Esta documentación
```

---

## 3. Configuración inicial

### 3.1 Instalar dependencias

```bash
cd scraper

# Crear entorno virtual
python3 -m venv .venv
source .venv/bin/activate       # macOS / Linux
# .venv\Scripts\activate        # Windows

# Instalar paquetes
pip install -r requirements.txt
```

**`requirements.txt`**

```
requests==2.32.3
beautifulsoup4==4.12.3
lxml==5.2.2
python-dotenv==1.0.1
flask==3.0.3
flask-cors==4.0.1
```

### 3.2 Crear fichero `.env`

```bash
cp .env.example .env
```

Editar `.env`:

```env
SHOPIFY_STORE=tu-tienda.myshopify.com
SHOPIFY_TOKEN=shpat_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
```

> ⚠️ El fichero `.env` está incluido en `.gitignore` y **nunca debe subirse al repositorio**.

---

## 4. Cómo obtener el token de Shopify

1. Entra en tu **Admin de Shopify** → `Settings` → `Apps and sales channels`
2. Haz clic en **Develop apps** (parte superior derecha)
3. Si es la primera vez, activa el desarrollo de apps con **Allow custom app development**
4. Clic en **Create an app** → pon un nombre (ej. `Product Importer`)
5. Ve a **Configuration** → **Admin API access scopes**
6. Activa los permisos:
   - `write_products` ← **obligatorio**
   - `read_products`  ← **obligatorio**
   - `write_inventory` ← opcional (para gestionar stock)
7. Clic en **Save** → **Install app**
8. En la pestaña **API credentials** encontrarás el **Admin API access token** (`shpat_...`)

> ⚠️ El token solo se muestra **una vez**. Cópialo en ese momento y guárdalo en tu `.env`.

---

## 5. Flujo completo paso a paso

```
Paso 1 → Scraping
         python scraper.py --category palas-2026 --pages 3
         └── Genera: scraped_products.json

Paso 2 → (Opcional) Descargar imágenes en local
         Se ejecuta automáticamente en el paso 1
         └── Guarda en: public/images/products/{categoria}/

Paso 3 → Comparar con Shopify
         El uploader consulta GET /products.json?fields=id,handle
         └── Detecta qué productos son nuevos vs. ya existentes

Paso 4 → Subir a Shopify
         python shopify_uploader.py --collection "Palas 2026"
         └── POST /products.json  (nuevos)
         └── PUT  /products/{id}.json  (actualizar existentes, con --update-existing)

Paso 5 → Asignar colección
         POST /collects.json
         └── Enlaza producto ↔ colección
```

### Diagrama de secuencia (subida de un producto)

```
uploader.py          Shopify Admin API
    │                      │
    │── GET /products ─────►│  Obtener handles existentes
    │◄── {handles: [...]} ──│
    │                      │
    │  [si es nuevo]        │
    │── POST /products ────►│  Crear producto con variante e imágenes
    │◄── {product: {id}} ───│
    │                      │
    │── POST /collects ────►│  Añadir a colección (si se especificó)
    │◄── {collect: {id}} ───│
    │                      │
    │  [si ya existe y --update-existing]
    │── PUT /products/{id} ►│  Actualizar precio, descripción, tags
    │── DEL /images/{id} ──►│  Borrar imágenes antiguas (una a una)
    │── POST /images ───────►│  Subir nuevas imágenes
    │◄── {image: {id}} ─────│
```

---

## 6. Módulo `scraper.py`

Extrae productos de **tiendapadelpoint.com** usando la API interna AJAX del sistema Journal2 SuperFilter.

### Categorías disponibles

| Slug | Path ID | Etiqueta |
|------|---------|----------|
| `palas-2026` | `60` | Palas 2026 |
| `zapatillas` | `83` | Zapatillas |
| `mochilas` | `86` | Mochilas y Paleteros |
| `pelotas` | `104` | Pelotas |
| `accesorios` | `135` | Accesorios |

### Funcionamiento interno

```python
# 1. Petición AJAX paginada
POST https://www.tiendapadelpoint.com/index.php
     ?route=module/journal2_super_filter/products
     &module_id=15
# payload: { route, path, sort, order, page, limit }

# 2. Parseo HTML con BeautifulSoup
#    - Extrae nombre, URL, precio, precio original, descuento, stock

# 3. Para cada producto: visita la página individual
#    - Extrae todas las imágenes del gallery (#product-gallery a[href])
#    - Fuerza resolución 1100×1100 en la URL

# 4. Descarga imágenes en paralelo (8 hilos)
#    - Destino: public/images/products/{categoria}/{slug}_{nn}.jpg

# 5. Genera scraped_products.json y src/data/products.ts
```

### Argumentos CLI

```bash
python scraper.py [opciones]

  --category palas-2026   Solo scrape de esa categoría
  --pages 3               Máximo de páginas por categoría (default: 5)
  --no-download           No descargar imágenes (solo JSON)
  --no-ts                 No generar products.ts
```

---

## 7. Módulo `shopify_uploader.py`

Se comunica con la **Shopify Admin REST API v2025-01**.

### Endpoints utilizados

| Método | Endpoint | Función |
|--------|----------|---------|
| `GET` | `/products.json?fields=id,handle&limit=250` | Obtener productos existentes |
| `POST` | `/products.json` | Crear nuevo producto |
| `PUT` | `/products/{id}.json` | Actualizar producto existente |
| `GET` | `/products/{id}/images.json` | Obtener imágenes actuales |
| `DELETE` | `/products/{id}/images/{img_id}.json` | Borrar imagen |
| `POST` | `/products/{id}/images.json` | Añadir imagen |
| `GET` | `/custom_collections.json?title=...` | Buscar colección |
| `POST` | `/custom_collections.json` | Crear colección |
| `POST` | `/collects.json` | Asignar producto a colección |

### Autenticación

Todas las peticiones llevan la cabecera:

```http
X-Shopify-Access-Token: shpat_xxxxxxxxxxxxxxxx
Content-Type: application/json
```

### Funciones principales

```python
get_existing_products_by_handle() → dict[handle, product_id]
# Consulta todos los productos y devuelve un dict para detección rápida de duplicados

build_product_payload(p: dict) → dict
# Construye el JSON completo del producto para la API de Shopify

create_product(p: dict) → str | None
# POST /products.json → devuelve el product_id creado

update_product(product_id: str, p: dict) → bool
# PUT /products/{id}.json + reemplaza imágenes

get_or_create_collection(title: str) → str
# Busca o crea una Custom Collection, devuelve su ID

add_to_collection(collection_id, product_id)
# POST /collects.json — enlaza producto con colección
```

### Argumentos CLI

```bash
python shopify_uploader.py [opciones]

  --json scraped_products.json    Fichero JSON de entrada (default: scraped_products.json)
  --collection "Palas 2026"       Asignar a esta colección (la crea si no existe)
  --limit 10                      Procesar solo los primeros N productos
  --dry-run                       Simular sin hacer cambios en Shopify
  --update-existing               Actualizar productos que ya existen (por handle)
  --skip-images                   No subir imágenes (útil para pruebas rápidas)
```

---

## 8. Dashboard web

Interfaz visual en `http://localhost:5050` construida con **Flask** (backend) y HTML/CSS/JS vanilla (frontend).

### Arranque

```bash
cd scraper
./run_dashboard.sh
```

El script:
1. Crea el entorno virtual `.venv` si no existe
2. Instala todas las dependencias de `requirements.txt`
3. Lanza `dashboard/app.py` en el puerto `5050`

### Vistas y funcionalidades

```
┌─────────────────────────────────────────────────────────┐
│  Header: badges de estado Shopify y scraping            │
├──────────────────┬──────────────────────────────────────┤
│  SIDEBAR         │  ÁREA PRINCIPAL                      │
│                  │                                      │
│  ┌────────────┐  │  Stats: total / nuevos / existentes  │
│  │ Shopify    │  │         / con descuento              │
│  │ Credenciales│ │                                      │
│  └────────────┘  │  Tabla de productos:                 │
│                  │  - Miniatura (clic → galería)        │
│  ┌────────────┐  │  - Nombre, marca, categoría          │
│  │ Scraping   │  │  - Precio, descuento                 │
│  │ PadelPoint │  │  - Badge Nuevo / En Shopify          │
│  │ [Iniciar]  │  │  - Stock                             │
│  └────────────┘  │  - Checkbox de selección             │
│                  │                                      │
│  ┌────────────┐  │  Filtros: búsqueda, estado, selección│
│  │ Subir a    │  │                                      │
│  │ Shopify    │  │  Log en tiempo real                  │
│  │ [Subir sel]│  │                                      │
│  └────────────┘  │                                      │
└──────────────────┴──────────────────────────────────────┘
```

### Modal de producto / galería

Al hacer clic en la miniatura de cualquier producto se abre un modal con:
- Galería de todas las imágenes con navegación por flechas y teclado
- Zoom con clic en la imagen principal
- Miniaturas clicables
- Info completa: nombre, marca, precio, descripción
- Enlace a la tienda original

---

## 9. API REST del dashboard

El backend Flask expone los siguientes endpoints:

### `GET /api/config`
Devuelve las credenciales guardadas (token enmascarado en UI).

```json
{
  "store": "mi-tienda.myshopify.com",
  "token": "shpat_xxxx",
  "configured": true
}
```

### `POST /api/config`
Guarda credenciales en el fichero `.env`.

```json
// Request
{ "store": "mi-tienda.myshopify.com", "token": "shpat_xxxx" }

// Response
{ "ok": true }
```

### `GET /api/products/local`
Devuelve el contenido de `scraped_products.json` (array de productos).

### `GET /api/products/shopify`
Consulta la tienda Shopify y devuelve los handles existentes.

```json
{ "handles": ["babolat-viper", "nox-ml10"], "total": 42 }
```

### `POST /api/scrape`
Inicia el scraping en un hilo background.

```json
// Request
{ "categories": ["palas-2026", "zapatillas"], "pages": 3 }

// Response
{ "ok": true }
```

### `GET /api/scrape/stream`
**Server-Sent Events** — stream de progreso del scraping en curso.

```
data: {"type": "log",      "msg": "📦 Scrapeando Palas 2026…"}
data: {"type": "progress", "category": "palas-2026", "count": 48}
data: {"type": "done",     "total": 48, "products": [...]}
data: {"type": "error",    "msg": "Connection timeout"}
data: {"type": "ping"}     ← keepalive cada 30s
```

### `GET /api/scrape/status`
```json
{ "running": false }
```

### `POST /api/upload`
Inicia la subida a Shopify en background.

```json
// Request
{
  "slugs": ["babolat-viper-23", "nox-ml10"],  // [] = todos los nuevos
  "collection": "Palas 2026",
  "updateExisting": false
}

// Response
{ "ok": true }
```

### `GET /api/upload/stream`
**Server-Sent Events** — progreso de la subida.

```
data: {"type": "log",      "msg": "✅ Creado: Babolat Viper → id=8123456"}
data: {"type": "progress", "current": 3, "total": 10, "name": "Nox ML10"}
data: {"type": "done",     "created": 8, "updated": 1, "skipped": 2, "errors": 0}
```

---

## 10. Modelo de datos del producto

Estructura del JSON generado por los scrapers y consumido por el uploader:

```json
{
  "slug":          "babolat-viper-carbon-2026",
  "name":          "Babolat Viper Carbon 2026",
  "brand":         "BABOLAT",
  "category":      "palas-2026",
  "price":         189.95,
  "originalPrice": 219.95,
  "discount":      14,
  "image":         "https://cdn.tiendapadelpoint.com/.../babolat-1100x1100.jpg",
  "images": [
    "https://cdn.tiendapadelpoint.com/.../babolat-1100x1100.jpg",
    "https://cdn.tiendapadelpoint.com/.../babolat-2-1100x1100.jpg"
  ],
  "inStock":       true,
  "description":   "Pala de control con núcleo de EVA...",
  "productUrl":    "https://www.tiendapadelpoint.com/palas/babolat-viper-carbon-2026",
  "localImage":    "/images/products/palas-2026/babolat-viper-carbon-2026_01.jpg",
  "localImages": [
    "/images/products/palas-2026/babolat-viper-carbon-2026_01.jpg",
    "/images/products/palas-2026/babolat-viper-carbon-2026_02.jpg"
  ]
}
```

| Campo | Tipo | Descripción |
|-------|------|-------------|
| `slug` | string | Identificador URL-friendly. Usado como `handle` en Shopify. **Clave de deduplicación.** |
| `name` | string | Nombre completo del producto |
| `brand` | string | Marca en mayúsculas |
| `category` | string | Slug de la categoría |
| `price` | float | Precio de venta actual |
| `originalPrice` | float? | Precio antes del descuento |
| `discount` | int? | Porcentaje de descuento |
| `image` | string | URL de la imagen principal |
| `images` | string[] | Todas las URLs remotas del producto |
| `inStock` | bool | Disponibilidad |
| `description` | string | Descripción corta (max 300 chars) |
| `productUrl` | string | URL en la tienda original |
| `localImage` | string | Ruta local de la imagen principal |
| `localImages` | string[] | Rutas locales de todas las imágenes |

---

## 11. Mapeo de campos a Shopify

| Campo scrapeado | Campo Shopify | Notas |
|-----------------|---------------|-------|
| `slug` | `product.handle` | Identificador único. Shopify genera URLs a partir de este campo. |
| `name` | `product.title` | |
| `brand` | `product.vendor` | Visible en el admin y filtros de tienda |
| `category` | `product.product_type` | |
| `description` | `product.body_html` | Se sube como HTML. El scraper devuelve texto plano. |
| `category` + `brand` | `product.tags` | Separados por coma. Se añade `sale` si hay descuento. |
| `inStock` | `product.published` | Producto no publicado si sin stock |
| `price` | `variants[0].price` | String con dos decimales |
| `originalPrice` | `variants[0].compare_at_price` | Precio tachado en la tienda |
| `inStock` | `variants[0].inventory_quantity` | `10` si hay stock, `0` si no |
| `images` / `localImages` | `product.images[]` | Ver sección siguiente |

### Payload completo enviado a `POST /products.json`

```json
{
  "product": {
    "title":        "Babolat Viper Carbon 2026",
    "handle":       "babolat-viper-carbon-2026",
    "vendor":       "BABOLAT",
    "product_type": "palas-2026",
    "body_html":    "Pala de control con núcleo de EVA...",
    "tags":         "palas-2026, BABOLAT, sale",
    "published":    true,
    "variants": [{
      "price":             "189.95",
      "compare_at_price":  "219.95",
      "inventory_management": "shopify",
      "inventory_quantity":   10,
      "fulfillment_service":  "manual",
      "requires_shipping":    true,
      "taxable":              true
    }],
    "images": [
      { "src": "https://cdn.tiendapadelpoint.com/.../img1.jpg", "position": 1, "alt": "Babolat Viper..." },
      { "src": "https://cdn.tiendapadelpoint.com/.../img2.jpg", "position": 2, "alt": "Babolat Viper..." }
    ]
  }
}
```

---

## 12. Gestión de imágenes

El uploader soporta **dos modos** de subida de imágenes:

### Modo A — URL remota (recomendado, más rápido)

Shopify descarga la imagen directamente desde la URL original.

```python
# Payload enviado:
{
  "src":      "https://cdn.tiendapadelpoint.com/image/cache/data/babolat-1100x1100.jpg",
  "position": 1,
  "alt":      "Babolat Viper Carbon 2026"
}
```

Se usa cuando `image` empieza por `http`.

### Modo B — Archivo local (base64)

Si la imagen fue descargada previamente, se codifica en base64 y se envía incrustada.

```python
# Payload enviado:
{
  "attachment": "iVBORw0KGgoAAAANSUhEUgAA...",  # base64
  "filename":   "babolat-viper-carbon-2026_01.jpg",
  "position":   1,
  "alt":        "Babolat Viper Carbon 2026"
}
```

### Prioridad de selección de imágenes

```
1. localImages[]   ← imágenes descargadas en public/images/products/
2. images[]        ← URLs remotas del scraper
3. [image]         ← imagen principal como fallback
```

### Actualización de imágenes en productos existentes

Al usar `--update-existing`, el proceso es:

```
GET  /products/{id}/images.json      → obtener IDs de imágenes actuales
DELETE /products/{id}/images/{img_id}.json  → borrar una a una (con 200ms entre cada una)
POST /products/{id}/images.json      → subir nuevas (con 300ms entre cada una)
```

---

## 13. Detección de duplicados

La deduplicación se basa en el campo **`handle`** (slug) del producto.

```python
# Al iniciar, el uploader consulta todos los productos de Shopify:
existing = get_existing_products_by_handle()
# → { "babolat-viper-carbon-2026": "8123456789", "nox-ml10": "8987654321", ... }

# Para cada producto scrapeado:
if product["slug"] in existing:
    if update_existing:
        update_product(existing[slug], product)  # actualiza
    else:
        skip()  # omite (comportamiento por defecto)
else:
    create_product(product)  # crea nuevo
```

> **Importante:** El `handle` en Shopify es único dentro de la tienda. Si intentas crear un producto con un handle ya existente, Shopify devuelve `422 Unprocessable Entity`.

---

## 14. Rate limiting y throttling

La Shopify Admin REST API tiene los siguientes límites:

| Plan | Req/seg | Bucket |
|------|---------|--------|
| Basic | 2 req/s | 40 calls |
| Shopify | 4 req/s | 80 calls |
| Advanced/Plus | 4 req/s | 80 calls |

El uploader respeta estos límites con **delays configurables**:

```python
REQUEST_DELAY = 0.6   # segundos entre productos (≈ 1.6 req/s, seguro para Basic)
```

Delays adicionales por operación:
- `0.2s` entre borrado de imágenes
- `0.3s` entre subida de imágenes  
- `0.3s` tras asignar colección

Si Shopify devuelve `429 Too Many Requests`, la petición fallará con un error HTTP. En ese caso, reducir el ritmo aumentando `REQUEST_DELAY`.

---

## 15. Uso por línea de comandos

### Flujo completo desde cero

```bash
# 1. Instalar dependencias
cd scraper
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# 2. Configurar credenciales
cp .env.example .env
# editar .env con tu store y token

# 3. Scrape de palas 2026 (3 páginas, con descarga de imágenes)
python scraper.py --category palas-2026 --pages 3

# 4. Probar en modo dry-run antes de subir
python shopify_uploader.py --dry-run --collection "Palas 2026"

# 5. Subir a Shopify
python shopify_uploader.py --collection "Palas 2026"
```

### Actualizar precios e imágenes de productos existentes

```bash
python scraper.py --category palas-2026 --no-download
python shopify_uploader.py --update-existing --skip-images
```

### Subir solo la fuente de Canaveral

```bash
python scraper_canaveral.py --pages 5
python shopify_uploader.py --json scraped_canaveral.json --collection "Palas 2026"
```

### Prueba con los primeros 5 productos

```bash
python shopify_uploader.py --limit 5 --dry-run
python shopify_uploader.py --limit 5 --collection "Test"
```

---

## 16. Casos de uso frecuentes

### A) Primera importación completa

```bash
python scraper.py --pages 5           # scrape todas las categorías
python shopify_uploader.py \
  --collection "Importación inicial"
```

### B) Sincronización periódica (solo novedades)

```bash
# Cada semana, scrape rápido sin descargar imágenes (más veloz)
python scraper.py --no-download

# Subir solo los que no existen en Shopify (default, sin --update-existing)
python shopify_uploader.py --collection "Palas 2026"
```

### C) Actualización masiva de precios

```bash
python scraper.py --no-download     # obtener precios actualizados
python shopify_uploader.py \
  --update-existing \
  --skip-images                     # solo actualiza datos, no reimporta imágenes
```

### D) Importar una categoría concreta al dashboard

1. Abre `http://localhost:5050`
2. En "Scraping · PadelPoint", selecciona solo `Zapatillas`
3. Haz clic en **Iniciar Scraping**
4. Cuando termine, filtra por "Solo nuevos"
5. Haz clic en **Sel. nuevos** → **Subir seleccionados**

---

## 17. Errores comunes y soluciones

### `401 Unauthorized`
El token no es válido o ha expirado.
→ Regenera el token en Shopify Admin y actualiza `.env`.

### `422 Unprocessable Entity` al crear producto
El `handle` ya existe en la tienda (duplicado silencioso).
→ Usa `--update-existing` o el uploader lo detecta automáticamente y lo omite.

### `429 Too Many Requests`
Demasiadas peticiones por segundo.
→ Aumenta `REQUEST_DELAY` en `shopify_uploader.py` (ej: `1.0` en lugar de `0.6`).

### Imágenes no aparecen en Shopify
Las URLs remotas del scraper pueden requerir autenticación o haber caducado.
→ Ejecuta el scraper con descarga local y sube los archivos en base64.

### `scraper.py` no encuentra productos (0 resultados)
El sitio puede haber cambiado su estructura HTML o el `MODULE_ID` de la API AJAX.
→ Inspecciona las peticiones XHR en el navegador y actualiza `MODULE_ID` en `scraper.py`.

### El dashboard no arranca (`ModuleNotFoundError`)
Las dependencias no están instaladas en el entorno virtual activo.
→ Usa siempre `./run_dashboard.sh` que gestiona el venv automáticamente.

### `Connection timeout` durante el scraping
La tienda original bloquea las peticiones por exceso de velocidad.
→ Reduce `DOWNLOAD_WORKERS` (ej: de 8 a 4) y aumenta `REQUEST_DELAY` en `scraper.py`.
