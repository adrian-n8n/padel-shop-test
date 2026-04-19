import os, hashlib, hmac, time, requests, re, json
from dotenv import load_dotenv
load_dotenv()

key    = os.environ['MIRAVIA_APP_KEY']
secret = os.environ['MIRAVIA_APP_SECRET']
token  = os.environ['MIRAVIA_ACCESS_TOKEN']
CATEGORY_ID = 62255292

def miravia_call(path, params=None, method='GET'):
    if params is None:
        params = {}
    p = {
        'app_key': key,
        'access_token': token,
        'timestamp': str(int(time.time() * 1000)),
        'sign_method': 'sha256',
        **params
    }
    base = path + ''.join(f'{k}{v}' for k, v in sorted(p.items()))
    p['sign'] = hmac.new(secret.encode(), base.encode(), hashlib.sha256).hexdigest().upper()
    url = 'https://api.miravia.es/rest' + path
    if method == 'GET':
        r = requests.get(url, params=p, timeout=30)
    else:
        r = requests.post(url, data=p, timeout=30)
    return r.json()

# 1. Obtener producto de Shopify
print('Obteniendo producto de Shopify...')
r = requests.get(
    'https://utrsp8-0c.myshopify.com/admin/api/2025-01/products/10322067063126.json',
    headers={'X-Shopify-Access-Token': os.environ['SHOPIFY_TOKEN']}
)
prod = r.json()['product']
variant = prod['variants'][0]
image_url = prod['images'][0]['src']
body_html = prod.get('body_html', '') or ''
barcode = variant.get('barcode') or variant['sku']  # EAN
description_html = body_html if body_html else f'<p>{prod["title"]}</p>'
additional_attrs = (
    'Material:Fibra de carbono 12K;'
    'Nucleo:EVA Soft;'
    'Forma:Lagrima/Redonda;'
    'Marco:Fibra de carbono;'
    'Nivel:Avanzado-Profesional;'
    'Balance:Medio-Alto'
)

print(f"  Título:  {prod['title']}")
print(f"  EAN:     {barcode}")
print(f"  Precio:  {variant['price']}")
print(f"  Marca:   {prod.get('vendor','')}")

# 2. PASO 1 — Crear producto con SKU temporal (el EAN)
# El item_id lo asigna Miravia en la respuesta
print('\n[1/3] Creando producto en Miravia...')
ts_create = str(int(time.time() * 1000))
xml_create = """<?xml version="1.0" encoding="UTF-8" ?>
<Request>
  <Product>
    <PrimaryCategory>{category}</PrimaryCategory>
    <Attributes>
      <name><![CDATA[{name}]]></name>
      <description><![CDATA[{description}]]></description>
      <brand><![CDATA[{brand}]]></brand>
      <Does_this_product_have_a_safety_warning>No</Does_this_product_have_a_safety_warning>
      <Format>Normal</Format>
      <shape>TEARDROP</shape>
      <Level>Profesional</Level>
      <Product_certificates>CE certificate</Product_certificates>
      <Additional_attributes><![CDATA[{additional}]]></Additional_attributes>
    </Attributes>
    <Skus>
      <Sku>
        <SellerSku>TEMP-{ean}</SellerSku>
        <ean_code>{ean}</ean_code>
        <quantity>{stock}</quantity>
        <price>{price}</price>
        <EU_Responsible>Padel el Canaveral SL</EU_Responsible>
        <package_weight>1</package_weight>
        <package_length>10</package_length>
        <package_width>30</package_width>
        <package_height>35</package_height>
      </Sku>
    </Skus>
    <Images>
      <Image>{image}</Image>
    </Images>
  </Product>
</Request>""".format(
    category=CATEGORY_ID,
    name=prod['title'],
    description=description_html,
    brand=prod.get('vendor', 'Starvie'),
    additional=additional_attrs,
    ean=barcode,
    stock=variant['inventory_quantity'],
    price=variant['price'],
    image=image_url,
)

resp_create = miravia_call('/product/create', {'payload': xml_create}, method='POST')
print(json.dumps(resp_create, indent=2, ensure_ascii=False))

if resp_create.get('code') != '0':
    print('\nError al crear el producto. Abortando.')
    exit(1)

item_id = resp_create['data']['item_id']
sku_id  = resp_create['data']['sku_list'][0]['sku_id']
# El timestamp de creación viene del sku_id que Miravia asigna internamente
# Usamos el timestamp actual de la petición para construir el SellerSku final
final_seller_sku = f'{item_id}-{ts_create}-0'
print(f'\n  item_id={item_id}  sku_id={sku_id}')
print(f'  SellerSku final: {final_seller_sku}')

# 3. PASO 2 — Renombrar SellerSku al formato estándar usando AssociatedSku
print('\n[2/3] Renombrando SellerSku al formato estándar...')
xml_rename = """<?xml version="1.0" encoding="UTF-8" ?>
<Request>
  <Product>
    <ItemId>{item_id}</ItemId>
    <Skus>
      <Sku>
        <SellerSku>TEMP-{ean}</SellerSku>
        <AssociatedSku>{final_sku}</AssociatedSku>
      </Sku>
    </Skus>
  </Product>
</Request>""".format(item_id=item_id, ean=barcode, final_sku=final_seller_sku)

resp_rename = miravia_call('/product/update', {'payload': xml_rename}, method='POST')
print(json.dumps(resp_rename, indent=2, ensure_ascii=False))

# 4. PASO 3 — Verificar resultado final
print('\n[3/3] Verificando producto...')
r = miravia_call('/products/get', {'filter': 'all', 'limit': '20', 'offset': '0'})
prods = r.get('data', {}).get('products', [])
for p in prods:
    if p.get('item_id') == item_id:
        skus = p.get('skus', [])
        s = skus[0] if skus else {}
        print(f'  Status:    {p.get("status")}')
        print(f'  SellerSku: {s.get("SellerSku")}')
        print(f'  URL:       {s.get("Url")}')
        break
