from chefagent.account_store import Store
import httpx,time
s=Store();key='storage-probe-'+str(time.time_ns());h={**s.headers(),'x-vercel-blob-access':'private','x-add-random-suffix':'0','x-content-type':'application/json','x-cache-control-max-age':'0'}
r=httpx.put('https://vercel.com/api/blob/',params={'pathname':'aurora/'+key+'.json'},headers=h,content='{"ok":true}',timeout=30)
d=r.json();print('PUT',r.status_code,'url',d.get('url'),'pathname',d.get('pathname'),'etag',bool(d.get('etag')))
for url in [s.url(key),d.get('url')]:
 if url:
  rr=httpx.get(url,headers=s.headers());print('GET',url,rr.status_code,rr.text[:100])
