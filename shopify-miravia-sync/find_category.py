import os
from dotenv import load_dotenv
load_dotenv()
from miravia_client import MiraviaClient

miravia = MiraviaClient(os.environ['MIRAVIA_APP_KEY'], os.environ['MIRAVIA_APP_SECRET'], os.environ['MIRAVIA_ACCESS_TOKEN'])
result = miravia._request('/category/tree/get', params={'language_code': 'es_ES'})
cats = result.get('data', [])

def buscar(cats, terminos, nivel=0):
    for c in cats:
        nombre = c.get('name','').lower()
        if any(t in nombre for t in terminos):
            print(' '*nivel + f"[{c['category_id']}] {c['name']} (leaf={c.get('leaf')})")
        buscar(c.get('children',[]), terminos, nivel+2)

buscar(cats, ['padel','raqueta','tenis','deporte','sport','pala'])
