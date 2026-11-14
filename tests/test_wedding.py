"""Hand-built expected order. No planner functions generate this expectation.
Example: Fri fish = 60×150g +120×150g -9kg remaining frozen fish =18kg.
Fri cream =60×60ml +120×45ml +120×30ml +40×35ml =14l =8×1.75l.
Egg =412×90g +120×35g -2kg stock =39.28kg => 8 cartons of5.2kg, split 2/3/3.
The golden expectation binds exact product IDs and pack-rounded sales units.
"""
from chefagent import kitchen as k
GOLD={
 '2026-11-16':{'460200':5,'464119':2,'463883':2,'474963':3,'463437':2,'471970':7,'475454':1,'475561':1,'464699':4},
 '2026-11-18':{'460200':6,'464119':3,'463883':3,'474963':3,'463437':5,'471970':14,'475454':5,'464699':5},
 '2026-11-20':{'460200':8,'464119':2,'463883':3,'474963':4,'463437':13,'461883':18,'471970':33,'475454':5,'465193':8,'471954':1,'469312':5,'476417':2,'460325':5},
}
def test_hand_built_wedding_order(wedding_state):
    o=k.build(wedding_state)
    assert {d['date']:{r['product_id']:r['units'] for r in d['rows']} for d in o['deliveries']}==GOLD
    assert {c['id'] for c in o['checks']}=={'swap','pack','budget'}
    assert next(r for r in o['rows'] if r['role']=='fish')['need']==18
    assert next(r for r in o['rows'] if r['product_id']=='465193')['need']==14

def test_all_rows_cover_need_and_each_sum_reconciles(wedding_state):
    for r in k.build(wedding_state)['rows']:
        assert abs(sum(a['amount'] for a in r['allocations'])-r['gross'])<1e-6
        assert abs(r['gross']-r['stock']-r['need'])<1e-6
        assert r['units']*r['pack']+1e-6>=r['need']
        assert (r['units']-1)*r['pack']<r['need']

def test_initial_order_needs_no_ok():
    o=k.build(k.initial_state())
    assert o['can_place'] and not o['checks']
    assert not any(r['role']=='fish' for r in o['rows'])

def test_smart_pack_all_used_in_booked_window(wedding_state):
    row=next(r for r in k.build(wedding_state)['rows'] if r['product_id']=='465193')
    assert row['ordered']==row['need']==14
    assert all(a['date'] in ('2026-11-20','2026-11-21','2026-11-22') for a in row['allocations'])

def test_large_pack_alternative_is_real_preference(wedding_state):
    o=k.act(k.seal(wedding_state),'small-cream')
    assert 'pack' not in [c['id'] for c in o['checks']]
    assert not any(r['product_id']=='465193' for r in o['rows'])
    assert next(r for r in o['rows'] if r['id']=='2026-11-20-cream')['units']==14
