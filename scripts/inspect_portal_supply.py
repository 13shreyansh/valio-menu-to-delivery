from chefagent.catalog import load
from chefagent.valio_api import ValioAPI
from chefagent.kitchen import pack_for
c=load();ids=['477032','464517','467319','468286']
for term in ['Juhla Mokka','Earl Grey','orange juice','whitefish','pike perch']:
 ps=c.search(term,k=4)
 print(term,[(p['id'],p['name'],p['pack']) for p,_ in ps]);ids +=[p['id'] for p,_ in ps]
a=ValioAPI(fresh=True)
for day in ['2026-11-16','2026-11-18','2026-11-20']:
 pr=a.price(day,ids);av=a.availability(day,ids)
 for pid in ids:
  p=c.get(pid);price=pr.get(pid,{});v=av.get(pid,{})
  try: pack=pack_for(p,price)[0]
  except Exception:pack='unconfirmed'
  print(day,pid,p['name'],price.get('unit_price'),pack,v.get('orderable'),v.get('available_date'),v.get('closing_time'))
