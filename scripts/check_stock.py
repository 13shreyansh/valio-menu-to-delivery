import httpx,json,concurrent.futures
base='https://valio-menu-to-delivery.vercel.app'
qs=['kirjolohi pakaste','kirjolohifilee pakaste','lohi kuutio pakaste','maito laktoositon','tilli pakaste']
def get(q):
 r=httpx.post(base+'/api/search',json={'query':q,'limit':30},timeout=180);r.raise_for_status();return q,r.json()
with concurrent.futures.ThreadPoolExecutor(max_workers=3) as ex:out=dict(ex.map(get,qs))
open('artifacts/stock-local.json','w').write(json.dumps(out,ensure_ascii=False,indent=2))
ids=list(dict.fromkeys(p['id'] for d in out.values() for p in d['results']))
quotes=[]
for start in range(0,len(ids),50):
 r=httpx.post(base+'/api/quote',json={'product_ids':ids[start:start+50],'delivery_date':'2026-11-20'},timeout=180);r.raise_for_status();quotes+=r.json()['quotes']
open('artifacts/stock-quotes-local.json','w').write(json.dumps(quotes,ensure_ascii=False,indent=2))
by={p['id']:p for d in out.values() for p in d['results']}
for p in quotes:
 av=p['availability']
 if av['model']=='Stock' and av['orderable']: print(p['id'],by[p['id']]['name_fi'],by[p['id']]['pack'],p['price']['unit_price'],av['closing_time'],av['amount'],by[p['id']]['contains'])
