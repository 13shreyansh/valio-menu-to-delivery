import uuid
import httpx,json
c=httpx.Client(headers={"x-valio-test-run":uuid.uuid4().hex},base_url='http://localhost:8077',timeout=180)
r=c.post('/api/login');cookie=r.cookies.get('aurora_account');c.headers['Cookie']='aurora_account='+cookie
r=c.post('/api/drafts');print('draft',r.status_code);oid=r.json()['draft_id']
with c.stream('POST','/api/ask',json={'draft_id':oid,'text':'Wedding on Saturday, 120 guests. Salmon soup, whitefish with potatoes, lemon tart.'}) as r:
 for line in r.iter_lines():
  if line.startswith('data: '):
   v=json.loads(line[6:]);print(v if v.get('type')!='result' else {'type':'result','question':v['order'].get('question'),'reading':v['order'].get('reading'),'total':v['order'].get('total'),'checks':[c['id'] for c in v['order'].get('checks',[])]},flush=True)
