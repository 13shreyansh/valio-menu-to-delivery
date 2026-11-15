import httpx, concurrent.futures, json
BASE='https://valio-menu-to-delivery.vercel.app'
queries=['lohifilee','kirjolohifilee','kuohukerma laktoositon','peruna','porkkana','voi laktoositon','sitruuna','vehnäjauho','sokeri','kananmuna','maito laktoositon','kaurahiutale','sipuli','tilli','siikafilee','juusto']
def one(q):
 r=httpx.post(BASE+'/api/search',json={'query':q,'limit':7},timeout=180);r.raise_for_status();return q,r.json()
with concurrent.futures.ThreadPoolExecutor(max_workers=3) as ex:
 out=dict(ex.map(one,queries))
open('artifacts/catalog-local.json','w').write(json.dumps(out,ensure_ascii=False,indent=2))
for q,d in out.items():
 print(q,[(p['id'],p['name_fi'],p['sales_unit'],p['pack'],p['pack_dim'],p['contains'],p['may_contain']) for p in d['results']])
