from chefagent.catalog import load
from chefagent.guardrails import product_violations
from chefagent.kitchen_fixtures import KITCHEN
cat=load()
for term in ['rye bread','yogurt','coffee','tea','orange juice','cucumber','tomato','siika','kuha','cream']:
 print('\n',term)
 for p,score in cat.search(term,k=30):
  if product_violations(p,policy=KITCHEN['policy']) or not p['pack']:continue
  print(p['id'], p['name'],p['name_fi'],p['pack'],p['pack_dim'],p['sales_unit'],p['contains'],p['may_contain'])
