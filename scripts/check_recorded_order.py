import sys,json
sys.path.insert(0,'.')
from chefagent import kitchen as k
from chefagent.kitchen_fixtures import WEDDING_TEXT
class Cat:
 def __init__(self):
  self.by={p['id']:p for f in ['artifacts/catalog-local.json','artifacts/more-local.json','artifacts/stock-local.json'] for data in json.load(open(f)).values() for p in data['results']}
 def get(self,pid): return self.by.get(pid)
class API:
 def __init__(self,**kw): self.audit=[]
 def price(self,day,ids):return {p['id']:p['price'] for p in quotes if p['id'] in ids}
 def availability(self,day,ids):return {p['id']:p['availability'] for p in quotes if p['id'] in ids}
quotes=json.load(open('artifacts/quotes-local.json'))['2026-11-16']['quotes']+json.load(open('artifacts/more-quotes-local.json'))+json.load(open('artifacts/stock-quotes-local.json'))
k.load=Cat;k.ValioAPI=API
s=k.initial_state();o=k.build(s);print('BASE',o['total'],[(c['id'],c['text']) for c in o['checks']])
s['wedding']={'date':'2026-11-21','covers':120,'dishes':[{'recipe':'salmon','covers':120},{'recipe':'tart','covers':120}],'transcript':WEDDING_TEXT}
o=k.build(s)
for d in o['deliveries']:
 print(d['date'],d['subtotal'])
 for r in d['rows']:print(r['role'],r['product_id'],r['units'],r['pack'],'need',r['gross'],'stock',r['stock'],'total',r['total'])
print('WEDDING',o['total'],[(c['id'],c['text']) for c in o['checks']])
json.dump(o,open('artifacts/wedding-local.json','w'),ensure_ascii=False,indent=2)
