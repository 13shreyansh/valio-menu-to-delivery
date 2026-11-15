import httpx, json, concurrent.futures
base='https://valio-menu-to-delivery.vercel.app'
search=json.load(open('artifacts/catalog-local.json'))
ids=list(dict.fromkeys(p['id'] for d in search.values() for p in d['results'] if p['id'] in ['461871','461907','461883','461895','461906','461908','461921','461940','469126','461273','464490','464699','464727','461490','465193','471970','469203','475454','475625','462421','463437','476417','460325','463883','464119','463380','460200','475561','461032','461947','469335','474187','474963','467659']))
def one(d):
 r=httpx.post(base+'/api/quote',json={'product_ids':ids,'delivery_date':d},timeout=180);r.raise_for_status();return d,r.json()
with concurrent.futures.ThreadPoolExecutor(max_workers=3) as ex: out=dict(ex.map(one,['2026-11-16','2026-11-18','2026-11-20']))
open('artifacts/quotes-local.json','w').write(json.dumps(out,ensure_ascii=False,indent=2))
for d,qs in out.items():
 print(d)
 for p in qs['quotes']:
  print(p['id'],p['name'],p['pack_kg_or_l'],p['price'],p['availability'])
