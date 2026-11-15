from chefagent.catalog import load
from chefagent.valio_api import ValioAPI
from chefagent.kitchen import pack_for,cutoff_passed
from chefagent.guardrails import product_violations
from chefagent.kitchen_fixtures import KITCHEN
c=load();a=ValioAPI()
for term in ['rye bread','cucumber','tomato']:
 ps=[p for p,_ in c.search(term,k=40) if p['pack'] and not product_violations(p,policy=KITCHEN['policy'])];ids=[p['id'] for p in ps];pr=a.price('2026-11-16',ids);av=a.availability('2026-11-16',ids)
 print(term)
 for p in ps:
  v=av.get(p['id'],{});q=pr.get(p['id'],{})
  if not v.get('orderable') or cutoff_passed(v.get('closing_time')):continue
  try:pack=pack_for(p,q)[0]
  except Exception:continue
  print(p['id'],p['name'],pack,q['unit_price'])
