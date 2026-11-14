import copy, json, time
import pytest
from chefagent import kitchen as k
from chefagent import valio_api as v
from .test_wedding import GOLD

def approved(s):
    out=k.response(s)
    for key in ['swap','pack','budget']: out=k.act(out['token'],'approve',key)
    return out

def test_budget_never_silently_exceeded(wedding_state):
    o=k.act(k.seal(wedding_state),'place')
    assert not o['can_place'] and 'confirmation' not in o
    assert any(c['id']=='budget' and not c['approved'] for c in o['checks'])
    assert approved(wedding_state)['can_place']

def test_budget_ok_invalidated_by_quantity(wedding_state):
    o=approved(wedding_state)
    row=next(r for r in o['rows'] if r['id']=='2026-11-20-cream')
    o=k.act(o['token'],'quantity',{'id':row['id'],'units':row['units']+1})
    assert not o['can_place']
    assert {'pack','budget'}<={c['id'] for c in o['checks'] if not c['approved'] and c['reopened']}
    assert 'confirmation' not in k.act(o['token'],'place')

def test_weekly_approval_is_for_whole_week(wedding_state):
    o=k.response(wedding_state)
    # Each delivery is small, but the weekly limit still applies.
    wedding_state['budget']=max(d['subtotal'] for d in o['deliveries'])+1
    assert k.build(wedding_state)['total']>wedding_state['budget']
    assert any(c['id']=='budget' for c in k.build(wedding_state)['checks'])

def test_price_change_invalidates_ok_at_commit(wedding_state,supplier):
    o=approved(wedding_state);supplier.price_factor=2
    o=k.act(o['token'],'place')
    assert not o['can_place'] and 'confirmation' not in o

def test_new_allergen_never_enters_order(wedding_state,supplier):
    supplier.new_allergens=True
    o=k.build(wedding_state)
    assert not o['can_place']
    assert not any('nuts' in r['contains'] for r in o['rows'])
    assert any(c['id'].startswith('gap-') for c in o['checks'])

def test_unavailable_products_cannot_be_approved(wedding_state,supplier):
    supplier.blocked={'461907','461883'}
    o=k.response(wedding_state)
    gap=next(c for c in o['checks'] if c['kind']=='gap')
    with pytest.raises(k.KitchenError): k.act(o['token'],'approve',gap['id'])

def test_shortage_cannot_be_approved(wedding_state):
    o=k.act(k.seal(wedding_state),'quantity',{'id':'2026-11-20-fish','units':1})
    assert any(c['id'].startswith('short-') and not c['can_approve'] for c in o['checks'])
    assert not o['can_place']

@pytest.mark.parametrize('units',[-1,1.5,True,10000])
def test_bad_quantity_rejected(wedding_state,units):
    with pytest.raises(k.KitchenError):k.act(k.seal(wedding_state),'quantity',{'id':'2026-11-20-fish','units':units})

def test_tampered_or_expired_approval_rejected(wedding_state):
    token=k.seal(wedding_state)
    with pytest.raises(k.KitchenError):k.unseal(token[:-1]+('0' if token[-1]!='0' else '1'))
    wedding_state['created']=time.time()-14401
    with pytest.raises(k.KitchenError):k.unseal(k.seal(wedding_state))

def test_cutoff_is_not_hidden():
    assert v._future_or_none('2020-01-01T15:00:00+0200')=='2020-01-01T15:00:00+0200'
    assert k.cutoff_passed(v._future_or_none('2020-01-01T15:00:00+0200'))

def test_customer_cache_does_not_leak(monkeypatch,tmp_path):
    path=tmp_path/'cache.json'
    path.write_text(json.dumps({'HC-A|/api/price|2026-11-20|P':{'at':time.time(),'row':{'productId':'P','catalogPrice':{'value':7}}}}))
    monkeypatch.setattr(v,'CACHE',path)
    a=v.ValioAPI(customer='HC-A',offline=True)
    b=v.ValioAPI(customer='HC-B',offline=True)
    assert a.price('2026-11-20',['P'])['P']['unit_price']==7
    assert b.price('2026-11-20',['P'])=={}

def test_expired_cache_is_not_current(monkeypatch,tmp_path):
    path=tmp_path/'cache.json'
    path.write_text(json.dumps({'HC-A|/api/price|2026-11-20|P':{'at':time.time()-121,'row':{'productId':'P'}}}))
    monkeypatch.setattr(v,'CACHE',path)
    a=v.ValioAPI(customer='HC-A');called=[]
    def fail(*args,**kw):called.append(True);raise RuntimeError('fresh supplier required')
    monkeypatch.setattr(v.httpx,'post',fail)
    with pytest.raises(RuntimeError):a.price('2026-11-20',['P'])
    assert called

def test_catalogue_cannot_add_duplicate_planned_product(wedding_state):
    with pytest.raises(k.KitchenError,match='already added'):
        k.act(k.seal(wedding_state),'add','471970')
