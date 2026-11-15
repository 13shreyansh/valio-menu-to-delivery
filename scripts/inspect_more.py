import httpx,json,concurrent.futures
base='https://valio-menu-to-delivery.vercel.app'
qs=['lohi filee pakaste','sitruuna tuore','sitruunamehu','tilli pakaste','juusto laktoositon gouda']
def one(q):
 r=httpx.post(base+'/api/search',json={'query':q,'limit':14},timeout=180);r.raise_for_status();return q,r.json()
with concurrent.futures.ThreadPoolExecutor(max_workers=3) as ex: out=dict(ex.map(one,qs))
open('artifacts/more-local.json','w').write(json.dumps(out,ensure_ascii=False,indent=2))
for q,d in out.items(): print(q,[(p['id'],p['name_fi'],p['pack'],p['sales_unit']) for p in d['results']])
ids=list(dict.fromkeys(p['id'] for d in out.values() for p in d['results']))
quotes=[]
for start in range(0,len(ids),50):
 r=httpx.post(base+'/api/quote',json={'product_ids':ids[start:start+50],'delivery_date':'2026-11-20'},timeout=180); r.raise_for_status();quotes.extend(r.json()['quotes'])
open('artifacts/more-quotes-local.json','w').write(json.dumps(quotes,ensure_ascii=False,indent=2))
for p in quotes: print(p['id'],p['price'].get('unit_price'),p['availability'])
