import uuid
"""Live acceptance over HTTP. Does not claim browser or microphone verification."""
import base64, concurrent.futures, json, sys, time
from pathlib import Path
import httpx
sys.path.insert(0,str(Path(__file__).resolve().parent.parent))
BASE=sys.argv[1] if len(sys.argv)>1 else 'https://valio-menu-to-delivery.vercel.app'
c=httpx.Client(headers={"x-valio-test-run":uuid.uuid4().hex},base_url=BASE,timeout=240)
def request(path,body=None):
 r=c.post('/api/sheet'+path,json=body) if body is not None else c.get('/api/sheet'+path)
 r.raise_for_status();return r.json()
previous_report=json.loads(Path('artifacts/live-verification.json').read_text()) if Path('artifacts/live-verification.json').exists() else {}
initial=request(''); assert initial['can_place'], initial['checks']
text=request('/tell',{'token':initial['token'],'text':'Wedding Saturday, 120 guests, salmon and lemon tart'})
assert text['reading']['status']=='readable',text
assert {c['id'] for c in text['checks']}=={'swap','pack','budget'},text['checks']
from tests.test_wedding import GOLD
assert {d['date']:{r['product_id']:r['units'] for r in d['rows']} for d in text['deliveries']}==GOLD
print('Measured live initial / wedding totals:',initial['total'],text['total'])
locked=request('/change',{'token':text['token'],'action':'place'})
assert 'confirmation' not in locked and not locked['can_place']
o=text
for key in ['swap','pack','budget']:o=request('/change',{'token':o['token'],'action':'approve','value':key})
assert o['can_place']
cream=next(r for r in o['rows'] if r['id']=='2026-11-20-cream')
changed=request('/change',{'token':o['token'],'action':'quantity','value':{'id':cream['id'],'units':cream['units']+1}})
assert not changed['can_place'] and {c['id'] for c in changed['checks'] if c['reopened']}=={'pack','budget'}

def photo(name):
 data=base64.b64encode(Path('public/whiteboards/'+name+'.jpg').read_bytes()).decode()
 r=request('/photo',{'token':o['token'],'media':{'mime':'image/jpeg','data':data}})
 return name,r
results=dict(photo(name) for name in ['menu-1','menu-2','menu-3','blank','garbled'])
expected={('whitefish',120),('tart',120),('cheeseboard',140)}
for name,r in results.items():
 reading=r['reading'];print(name,reading['status'],reading['dishes'],reading['transcript'][:100])
 if name.startswith('menu-'):
  assert reading['status']=='readable' and reading['covers']==120
  assert {(d['recipe'],d['covers']) for d in reading['dishes']}==expected
 else:
  assert reading['status']!='readable'
  rr=c.post('/api/sheet/photo/apply',json={'token':o['token'],'read_token':r['read_token'],'reading':results['menu-1']['reading']})
  assert rr.status_code==422
final=request('/photo/apply',{'token':results['menu-1'].get('token',o['token']),'read_token':results['menu-1']['read_token'],'reading':results['menu-1']['reading']})
assert next(r for r in final['rows'] if r['role']=='whitefish')['units']==18
for ch in list(final['checks']):
 if not ch['approved']: final=request('/change',{'token':final['token'],'action':'approve','value':ch['id']})
placed=request('/change',{'token':final['token'],'action':'place'})
assert placed.get('confirmation',{}).get('demo') is True
r=c.post('/mcp/',headers={'Accept':'application/json, text/event-stream'},json={'jsonrpc':'2.0','id':1,'method':'tools/list','params':{}})
r.raise_for_status();tools=r.json()['result']['tools'];assert any(t['name']=='request_order' for t in tools)
if not Path('public/story-readings.json').exists(): Path('public/story-readings.json').write_text(json.dumps({'wedding':text['reading'],'photo':results['menu-1']['reading'],'provenance':{'source':'Actual Gemini responses from live deployment','verified_at':time.strftime('%Y-%m-%dT%H:%M:%S%z'),'images':['menu-1.jpg','menu-2.jpg','menu-3.jpg'],'note':'Story uses recorded understanding for reliability; supplier quotes and approvals run normally.'}},indent=2,ensure_ascii=False))
report={'base':BASE,'measured_at':time.strftime('%Y-%m-%dT%H:%M:%S%z'),'initial_total':initial['total'],'wedding_total':text['total'],'final_total':placed['total'],'order_number':placed['confirmation']['order_number'],'rows_matched_hand_gold':sum(len(v) for v in GOLD.values()),'photo_results':{n:r['reading'] for n,r in results.items()},'mcp_tools':[t['name'] for t in tools],'browser_verified':False,'microphone_verified':False,'deployment_commit':c.get('/api/health').json().get('build_commit')}
if previous_report.get('audio_test'): report['audio_test']=previous_report['audio_test']
Path('artifacts/live-verification.json').write_text(json.dumps(report,indent=2,ensure_ascii=False))
print('Measured: expected order, budget lock, stale approval, 3 positive +2 negative photos, final mock confirmation and MCP passed.')
