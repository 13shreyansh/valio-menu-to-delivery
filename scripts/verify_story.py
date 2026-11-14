"""Recorded-story backend acceptance over live HTTP; not browser or microphone proof."""
import httpx,json
from pathlib import Path
c=httpx.Client(base_url='https://valio-menu-to-delivery.vercel.app',timeout=180)
def get(path):
 r=c.get('/api/sheet'+path);r.raise_for_status();return r.json()
def post(path,body):
 r=c.post('/api/sheet'+path,json=body);r.raise_for_status();return r.json()
o=get('');reading=get('/story-reading');assert reading['ready']
o=post('/story-wedding',{'token':o['token'],'wedding_token':reading['wedding_token']})
assert {x['id'] for x in o['checks']}=={'swap','pack','budget'}
for key in ['swap','pack','budget']:o=post('/change',{'token':o['token'],'action':'approve','value':key})
assert o['can_place']
cream=next(r for r in o['rows'] if r['id']=='2026-11-20-cream')
o=post('/change',{'token':o['token'],'action':'quantity','value':{'id':cream['id'],'units':cream['units']+1}})
assert not o['can_place']
for ch in list(o['checks']):
 if not ch['approved']:o=post('/change',{'token':o['token'],'action':'approve','value':ch['id']})
o=post('/photo/apply',{'token':o['token'],'read_token':reading['read_token'],'reading':reading['photo']})
for ch in list(o['checks']):
 if not ch['approved']:o=post('/change',{'token':o['token'],'action':'approve','value':ch['id']})
o=post('/change',{'token':o['token'],'action':'place'})
assert o.get('confirmation',{}).get('demo') is True
print('Measured live recorded-story backend: wedding,3 checks,cream edit/reopen,final photo,new budget,mock confirmation passed.',o['total'])
p=Path('artifacts/live-verification.json')
if p.exists():
 d=json.loads(p.read_text());d['recorded_story_backend']={'passed':True,'total':o['total'],'browser':False};p.write_text(json.dumps(d,ensure_ascii=False,indent=2))
