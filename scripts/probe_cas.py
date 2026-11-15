from chefagent.account_store import Store
import httpx,time
s=Store();key='cas-probe-'+str(time.time_ns());v=s.put(key,{'n':1});d,w=s.get(key);print('PUT ETag',v,'GET ETag',w)
r=httpx.get('https://vercel.com/api/blob/',params={'url':s.url(key)},headers=s.headers());print('HEAD via API',r.status_code,r.text[:500])
for version in [w,w.strip('"') if w else w,v]:
 try:print('write version',version,s.put(key,{'n':2},version));break
 except Exception as e:print(type(e).__name__,str(e))
