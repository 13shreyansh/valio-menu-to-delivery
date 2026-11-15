from chefagent.account_store import Store
import httpx
s=Store();key='drafts/f078d6a37295443d9467ed4b515b7a84'
a=httpx.get(s.url(key),headers=s.headers());b=httpx.get('https://vercel.com/api/blob/',params={'url':s.url(key)},headers=s.headers());print('GET etag',a.headers.get('etag'),'encoding',a.headers.get('content-encoding'),'len',len(a.content));print('HEAD etag',b.json().get('etag'));print('same',a.headers.get('etag')==b.json().get('etag'))
c=httpx.get(s.url(key),headers={**s.headers(),'Accept-Encoding':'identity'});print('identity',c.headers.get('etag'),'encoding',c.headers.get('content-encoding'))
