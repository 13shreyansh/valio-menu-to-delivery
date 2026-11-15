import uuid
import httpx,json,base64
c=httpx.Client(headers={"x-valio-test-run":uuid.uuid4().hex},base_url='https://valio-menu-to-delivery.vercel.app',timeout=180)
print('Build',c.get('/api/health').json().get('build_commit'),flush=True)
c.post('/api/login');o=c.post('/api/drafts').json();print('Draft ready',flush=True)
with c.stream('POST','/api/ask',json={'draft_id':o['draft_id'],'media':{'mime':'image/jpeg','data':base64.b64encode(open('public/whiteboards/menu-1.jpg','rb').read()).decode()}}) as r:
 for line in r.iter_lines():
  if line.startswith('data: '):
   v=json.loads(line[6:])
   if v['type']=='result':print({key:v['order'].get(key) for key in ['question','reading','total','pending']},flush=True)
   else:print(v,flush=True)
