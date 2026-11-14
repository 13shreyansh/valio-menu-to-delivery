"""Synthetic supplier for isolated tests. These €1 quotes never enter the app."""
import copy, datetime as dt
import pytest
from chefagent import kitchen as k
from chefagent.kitchen_fixtures import INGREDIENTS
PACKS={'461907':1,'469560':1,'469335':1,'471970':1,'475454':2.5,'475561':10,
       '464699':1,'465193':1.75,'463437':.5,'463380':1,'460200':1,
       '463883':5.2,'474963':1,'476417':4,'460325':1,'469312':1,'471954':2}
class Supplier:
    blocked={'461907'}
    new_allergens=False
    price_factor=1
    def __init__(self,**kwargs): self.audit=[]
    def price(self,date,ids):
        return {pid:{'unit_price':self.price_factor,'comparison_price':round(self.price_factor/PACKS[pid],5), 'error':False} for pid in ids}
    def availability(self,date,ids):
        return {pid:{'orderable':pid not in self.blocked,'available_date':date,'amount':10000,'model':'Stock',
                     'closing_time':(dt.datetime.now(dt.timezone.utc)+dt.timedelta(days=2)).isoformat()} for pid in ids}
class Catalog:
    def get(self,pid):
        if pid not in PACKS:return None
        role=next(r for r,s in INGREDIENTS.items() if pid in s['ids'])
        contains=['fish'] if role in ('fish','whitefish') else ['milk'] if role in ('cream','milk','butter','cheese') else ['gluten'] if role in ('flour','oats') else ['egg'] if role=='egg' else []
        return {'id':pid,'name':role,'name_fi':role,'pack':PACKS[pid],
                'pack_dim':INGREDIENTS[role]['unit'],'sales_unit':'KG' if role in ('fish','whitefish') else 'ST',
                'contains':contains+(['nuts'] if Supplier.new_allergens and pid=='469560' else []),
                'may_contain':[],'category':'test','lactose_free':True}
@pytest.fixture(autouse=True)
def supplier(monkeypatch):
    monkeypatch.setenv('KITCHEN_SIGNING_KEY','isolated-unit-test-key')
    monkeypatch.setattr(k,'load',Catalog);monkeypatch.setattr(k,'ValioAPI',Supplier)
    Supplier.blocked={'461907'};Supplier.new_allergens=False;Supplier.price_factor=1
    return Supplier
@pytest.fixture
def wedding_state():
    s=k.initial_state();s['budget']=1
    s['wedding']={'date':'2026-11-21','covers':120,'dishes':[{'recipe':'salmon','covers':120},{'recipe':'tart','covers':120}],'transcript':'Wedding Saturday, 120 guests, salmon and lemon tart'}
    return s
