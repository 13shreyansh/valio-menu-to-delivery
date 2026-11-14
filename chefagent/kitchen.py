"""Deterministic Kitchen Sheet. Gemini interprets; this module owns every number.
A signed, expiring state travels with the sheet, so Vercel needs no in-memory session.
Approval fingerprints bind the chef's OK to the current products, amounts and prices.
"""
import base64, copy, datetime as dt, hashlib, hmac, json, math, os, time
from collections import defaultdict
from decimal import Decimal, ROUND_CEILING
from zoneinfo import ZoneInfo
from .catalog import load
from .guardrails import product_violations
from .valio_api import ValioAPI
from .kitchen_fixtures import KITCHEN, INGREDIENTS, STOCK, RECIPES, BASE_SERVICES, DELIVERIES

TZ = ZoneInfo('Europe/Helsinki')
class KitchenError(ValueError): pass

def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=False).encode()).hexdigest()

def signing_key():
    key = os.environ.get('KITCHEN_SIGNING_KEY') or os.environ.get('VALIO_API_KEY')
    if not key: raise KitchenError('The kitchen connection is not configured.')
    return hmac.new(key.encode(), b'valio-kitchen-sheet-state-v1', hashlib.sha256).digest()

def seal(state):
    raw = base64.urlsafe_b64encode(json.dumps(state, separators=(',', ':'), ensure_ascii=False).encode()).decode()
    sig = hmac.new(signing_key(), raw.encode(), hashlib.sha256).hexdigest()
    return raw + '.' + sig

def unseal(token):
    try:
        raw, sig = token.rsplit('.', 1)
        if len(raw) > 500000 or not hmac.compare_digest(sig, hmac.new(signing_key(), raw.encode(), hashlib.sha256).hexdigest()):
            raise KitchenError('This sheet changed outside the kitchen. Reload it.')
        state = json.loads(base64.urlsafe_b64decode(raw))
        if time.time() - state['created'] > 14400: raise KitchenError('This sheet expired. Reload to check prices again.')
        return state
    except (KeyError, ValueError, TypeError) as e:
        if isinstance(e, KitchenError): raise
        raise KitchenError('This sheet could not be checked. Reload it.') from None

def initial_state():
    return {'created': time.time(), 'wedding': None, 'budget': KITCHEN['budget'], 'overrides': {},
            'approvals': {}, 'events': [], 'calls': [], 'extra': []}

def services_for(state):
    services = copy.deepcopy(BASE_SERVICES)
    w = state.get('wedding')
    if w:
        for dish in w['dishes']:
            services.append({'date': w['date'], 'recipe': dish['recipe'], 'covers': dish['covers'], 'wedding': True})
    return services

def delivery_for(date): return max(d for d in DELIVERIES if d <= date)

def round_units(amount, pack):
    if amount <= 0: return 0
    return int((Decimal(str(round(amount, 6))) / Decimal(str(pack))).to_integral_value(rounding=ROUND_CEILING))

def pack_for(p, price):
    if p['sales_unit'] == 'KG': return 1., 'Valio sales unit, kg'
    declared = p.get('pack')
    cp, up = price.get('comparison_price'), price.get('unit_price')
    if cp and up:
        ratio = up / cp
        if declared and abs(declared-ratio) <= declared*.03: return declared, 'Catalogue pack confirmed by Valio price comparison'
        # Price ratios are rounded: a disagreement must stop automatic ordering.
        raise KitchenError(f"Pack size needs checking for {p.get('name_fi') or p['id']}.")
    if declared and p.get('pack_dim') in ('kg', 'l'):
        return declared, 'Catalogue pack; Valio has no comparison price'
    raise KitchenError(f"No pack size for {p.get('name_fi') or p['id']}.")

def cutoff_passed(value):
    if not value: return False
    try: return dt.datetime.fromisoformat(value.replace('Z', '+00:00')) <= dt.datetime.now(TZ)
    except (ValueError, TypeError): return True

def build(state, fresh=False):
    cat, api = load(), ValioAPI(customer=KITCHEN['customer'], fresh=fresh)
    allocations = defaultdict(list)
    for s in services_for(state):
        recipe = RECIPES[s['recipe']]
        for role, grams in recipe['ingredients'].items():
            allocations[(delivery_for(s['date']), role)].append({
                'dish': recipe['name'], 'date': s['date'], 'covers': s['covers'],
                'per_cover': grams, 'amount': round(s['covers']*grams/1000, 6),
                'wedding': s.get('wedding', False)})
    remaining = copy.deepcopy(STOCK)
    rows, checks, reasons = [], [], []
    cream_rows, swaps = [], []
    for day in DELIVERIES:
        roles = [r for (d,r) in allocations if d == day]
        ids = list(dict.fromkeys(pid for role in roles for pid in INGREDIENTS[role]['ids']))
        prices, avails = api.price(day, ids), api.availability(day, ids)
        for role in roles:
            parts = allocations[(day,role)]
            gross = round(sum(p['amount'] for p in parts), 6)
            used_stock = min(remaining[role], gross)
            remaining[role] = round(remaining[role] - used_stock, 6)
            net = round(gross-used_stock, 6)
            if net <= 0: continue
            candidates = []
            for pid in INGREDIENTS[role]['ids']:
                p, pr, av = cat.get(pid), prices.get(pid,{}), avails.get(pid,{})
                if not p or pr.get('error') or pr.get('unit_price') is None: continue
                violations = product_violations(p, policy=KITCHEN['policy'])
                if role in ('fish','whitefish') and 'fish' not in p['contains']:
                    violations.append('Fish allergen is not declared; cannot prove safe replacement.')
                if role == 'fish' and pid != INGREDIENTS[role]['ids'][0]:
                    original = cat.get(INGREDIENTS[role]['ids'][0])
                    if not original or set(p['contains'])-set(original['contains']) or set(p['may_contain'])-set(original['may_contain']):
                        violations.append('Replacement introduces a new allergen.')
                if violations:
                    reasons.append({'product': pid, 'reason': '; '.join(violations), 'decision': 'Excluded'})
                    continue
                if not av.get('orderable') or (av.get('available_date') or '9999') > day: continue
                if cutoff_passed(av.get('closing_time')):
                    reasons.append({'product':pid,'reason':'Supplier cut-off passed for this delivery.','decision':'Excluded'})
                    continue
                try: pack, source = pack_for(p,pr)
                except KitchenError: continue
                units = round_units(net, pack)
                if units > (av.get('amount') or 0): continue
                candidates.append((p,pr,av,pack,source,units))
            # Cream: compare the real customer prices, and limit pack size to demand
            # within the kitchen's 48-hour opened-pack window. No 20 l upsell.
            if role == 'cream' and day == DELIVERIES[-1] and state.get('wedding') and not state.get('small_cream'):
                demand48 = sum(x['amount'] for x in parts if x['date'] <= (dt.date.fromisoformat(day)+dt.timedelta(days=2)).isoformat())
                candidates.sort(key=lambda c: (c[1]['unit_price']/c[3] if c[3] <= demand48 else float('inf'), c[3]))
            if not candidates:
                checks.append({'id':'gap-'+day+'-'+role,'kind':'gap','text':f'No safe {role} can be confirmed for {day}. Change the menu or restore supply.',
                               'button':'Check menu','blocking':True,'can_approve':False,'row_ids':[]})
                continue
            p,pr,av,pack,source,units = candidates[0]
            rid = day+'-'+role
            planned = units
            units = state['overrides'].get(rid, units)
            purchased = round(units*pack, 6)
            remaining[role] += max(0,purchased-net) if role != 'cream' else 0
            amount = round(pr['unit_price']*units, 2)
            row = {'id':rid,'role':role,'product_id':p['id'],'name':p['name_fi'] or p['name'],
                   'delivery':day,'unit':INGREDIENTS[role]['unit'],'sales_unit':p['sales_unit'],
                   'pack':pack,'pack_source':source,'units':units,'planned_units':planned,
                   'gross':gross,'stock':round(used_stock,6),'need':net,'ordered':purchased,
                   'unit_price':pr['unit_price'],'comparison_price':pr.get('comparison_price'),
                   'comparison_unit':pr.get('comparison_unit'),'total':amount,'availability':av,
                   'contains':p['contains'],'may_contain':p['may_contain'],'allocations':parts,
                   'change':None,'reason':'Menu × booked covers, less usable stock, rounded up to sales units.'}
            if state.get('wedding') and any(x.get('wedding') for x in parts):
                row['change'] = 'More' if any(not x.get('wedding') for x in parts) else 'Added'
                row['change_reason'] = 'for the new wedding menu' if state['wedding'].get('from_photo') else 'for Saturday wedding'
            if role == 'fish' and p['id'] != INGREDIENTS['fish']['ids'][0]:
                row['change']='Swapped'
                original = cat.get(INGREDIENTS['fish']['ids'][0])
                row['change_reason']='was '+(original['name_fi'] or original['name'])
                row['reason']='Salmon has no confirmed delivery in time. Thaw the raw trout fillet chilled and cut 150 g portions before gently poaching, as the kitchen recipe requires. Same fish weight, no new allergens.'
                swaps.append(row)
            if role == 'cream' and p['id'] != INGREDIENTS['cream']['ids'][0]:
                alternatives = [c for c in candidates if c[0]['id']==INGREDIENTS['cream']['ids'][0]]
                if alternatives:
                    small = alternatives[0]
                    saving = small[1]['unit_price']/small[3]-pr['unit_price']/pack
                    row['reason']=f'{pack:g} l pack is €{saving:.2f} less per litre than the 1 l pack. {net:g} l needed in booked recipes; opened packs used within 48 h, under the kitchen handling rule.'
                    row['pack_saving_per_l']=round(saving,2)
                    cream_rows.append(row)
            if units > (av.get('amount') or 0):
                checks.append({'id':'stock-'+rid,'kind':'gap','text':f'{row["name"]}: not enough confirmed Valio stock. Reduce the quantity or change the menu.', 'button':'Restore quantity','blocking':True,'can_approve':False,'row_ids':[rid]})
            if purchased+1e-6 < net:
                checks.append({'id':'short-'+rid,'kind':'gap','text':f'{row["name"]}: {net-purchased:g} {row["unit"]} still needed. Put back the recipe quantity.',
                               'button':'Restore quantity','blocking':True,'can_approve':False,'row_ids':[rid]})
            if cutoff_passed(av.get('closing_time')):
                checks.append({'id':'cutoff-'+rid,'kind':'gap','text':f'{row["name"]}: Valio cut-off passed. A new delivery must be confirmed before placing.',
                               'button':'Check delivery','blocking':True,'can_approve':False,'row_ids':[rid]})
            rows.append(row)
    # Explicit chef additions from catalogue, never from the model.
    for extra in state.get('extra',[]):
        p = cat.get(extra['product_id'])
        if not p or product_violations(p, policy=KITCHEN['policy']): raise KitchenError('This product breaks the kitchen rules.')
        day=DELIVERIES[-1]; pid=p['id']; pr=api.price(day,[pid]).get(pid,{}) ; av=api.availability(day,[pid]).get(pid,{})
        if not av.get('orderable') or (av.get('available_date') or '9999')>day or pr.get('error') or pr.get('unit_price') is None or cutoff_passed(av.get('closing_time')):
            raise KitchenError('Valio cannot confirm this product for Friday. Choose another product.')
        pack,source=pack_for(p,pr); units=state['overrides'].get('extra-'+pid,extra['units'])
        if units>av.get('amount',0): raise KitchenError('Not enough stock for this addition.')
        rows.append({'id':'extra-'+pid,'role':'extra','product_id':pid,'name':p['name_fi'] or p['name'], 'delivery':day,
                     'unit':p.get('pack_dim') or 'kg','sales_unit':p['sales_unit'],'pack':pack,'pack_source':source,
                     'units':units,'planned_units':units,'gross':units*pack,'stock':0,'need':units*pack,'ordered':units*pack,
                     'unit_price':pr['unit_price'],'total':round(units*pr['unit_price'],2),'availability':av,
                     'contains':p['contains'],'may_contain':p['may_contain'],'allocations':[],
                     'change':'Added','change_reason':'by the chef','reason':'Chef added this product.'})
    previous={r['id']:r for r in state.get('previous_rows',[])}
    for row in rows:
        old=previous.get(row['id'])
        if not old:
            if row.get('change') != 'Swapped' and previous:
                row['change']='Added';row['change_reason']='for the new wedding menu' if state.get('wedding',{}).get('from_photo') else 'for Saturday wedding'
        elif row['product_id'] != old['product_id']:
            row['change']='Swapped';row['change_reason']='was '+old['name']
        elif row['units'] != old['units']:
            row['change']='More' if row['units']>old['units'] else 'Less'
            row['change_reason']='for the new wedding menu' if state.get('wedding',{}).get('from_photo') else 'for Saturday wedding'
        elif previous:
            row['change']=None
    for rid,old in previous.items():
        if rid not in {r['id'] for r in rows} and old['units']>0:
            removed=copy.deepcopy(old)
            removed.update({'units':0,'planned_units':0,'gross':0,'stock':0,'need':0,'ordered':0,'total':0,'allocations':[],
                            'change':'Removed','change_reason':'for the new wedding menu','reason':'Removed from the wedding menu.'})
            rows.append(removed)
    if swaps:
        first=swaps[0]
        checks.append({'id':'swap','kind':'swap','text':f'Salmon has no confirmed delivery in time. Swap to {first["name"]}: cut 150 g portions in the kitchen, then gently poach. Same fish weight, no new allergens.',
                       'button':'OK, swap','alternative':'Change menu','row_ids':[r['id'] for r in swaps], 'can_approve':True,
                       'proof':'Fish → fish. No nuts, peanuts or new may-contain allergens.'})
    if cream_rows:
        first=cream_rows[-1]
        checks.append({'id':'pack','kind':'pack','text':f'{first["name"]}: €{first["pack_saving_per_l"]:.2f} less per litre than 1 l. Buy {first["units"]} × {first["pack"]:g} l for {first["need"]:g} l of booked recipes.',
                       'button':'OK, larger pack','alternative':'Keep 1 l','row_ids':[r['id'] for r in cream_rows], 'can_approve':True,
                       'proof':'Kitchen rule: opened cream used within 48 h. The pack is smaller than the booked demand in that window.'})
    total = round(sum(r['total'] for r in rows),2)
    if total>state['budget']:
        checks.append({'id':'budget','kind':'budget','text':f'This order is €{total-state["budget"]:.2f} over your weekly budget of €{state["budget"]:,.2f}.',
                       'button':'OK this week','alternative':'Show costliest','row_ids':[r['id'] for r in rows], 'can_approve':True,
                       'proof':'An OK applies only to these products, quantities and prices. Your weekly budget stays unchanged.'})
    row_by_id={r['id']:r for r in rows}
    for check in checks:
        check['fingerprint']=digest([check['id'],state['budget'] if check['id']=='budget' else None,
            [[rid,row_by_id[rid]['product_id'],row_by_id[rid]['units'],row_by_id[rid]['unit_price']] for rid in check['row_ids']]])
        ack=state['approvals'].get(check['id'])
        check['approved']=bool(ack and ack['fingerprint']==check['fingerprint'] and check['can_approve'])
        check['approved_at']=ack.get('at') if check['approved'] else None
        check['reopened']=bool(ack and not check['approved'])
    for r in rows: reasons.append({'product':r['product_id'],'row':r['id'],'reason':r['reason'],'decision':r.get('change') or 'Menu'})
    deliveries=[]
    for d in DELIVERIES:
        group=[r for r in rows if r['delivery']==d]
        if not group: continue
        cutoffs=[r['availability']['closing_time'] for r in group if r['availability'].get('closing_time')]
        deliveries.append({'date':d,'rows':group,'subtotal':round(sum(r['total'] for r in group),2),
                           'cutoff':min(cutoffs) if cutoffs else None,
                           'cutoff_note':'Earliest cut-off returned by Valio. Terminal cut-off not supplied.' if any(r['availability'].get('model')=='Terminal' and not r['availability'].get('closing_time') for r in group) else 'Valio cut-off'})
    state['calls']=(state.get('calls',[])+api.audit)[-300:]
    return {'rows':rows,'deliveries':deliveries,'total':total,'budget':state['budget'],'checks':checks,
            'pending':sum(not c['approved'] for c in checks),'can_place':all(c['approved'] for c in checks),
            'kitchen':KITCHEN,'stock':STOCK,'recipes':RECIPES,'services':services_for(state),
            'wedding':state.get('wedding'),'quote_at':dt.datetime.now(TZ).isoformat(),
            'evidence':{'calls':state['calls'],'decisions':reasons,'events':state['events'],'guardrails':KITCHEN['rules'],
                        'fixture_note':KITCHEN['fixture_note'],'price_note':'Customer HC-1001 prices, excluding VAT. Final ordering is a demo confirmation; Valio provides no order endpoint.'}}

def response(state, fresh=False):
    order=build(state,fresh=fresh)
    order['token']=seal(state)
    return order

def act(token, action, value=None):
    state=unseal(token)
    before=build(state)
    if action=='approve':
        check=next((c for c in before['checks'] if c['id']==value),None)
        if not check or not check['can_approve']: raise KitchenError('This needs a menu or delivery change, not an OK.')
        state['approvals'][value]={'fingerprint':check['fingerprint'],'at':dt.datetime.now(TZ).strftime('%H:%M')}
        state['events'].append({'action':'OK','check':value,'at':dt.datetime.now(TZ).isoformat(),'fingerprint':check['fingerprint']})
    elif action=='unapprove': state['approvals'].pop(value,None)
    elif action=='quantity':
        rid=value['id']; units=value['units']
        if not isinstance(units,int) or isinstance(units,bool) or not 0<=units<=9999: raise KitchenError('Use a whole number of sales units, from 0 to 9999.')
        if rid not in {r['id'] for r in before['rows']}: raise KitchenError('That product is no longer on this sheet.')
        state['overrides'][rid]=units
        state['events'].append({'action':'Chef quantity','row':rid,'units':units,'at':dt.datetime.now(TZ).isoformat()})
    elif action=='budget':
        if not isinstance(value,(int,float)) or isinstance(value,bool) or not math.isfinite(value) or not 0<value<=1000000: raise KitchenError('Enter a weekly budget above zero.')
        state['budget']=round(value,2)
        state['events'].append({'action':'Chef weekly budget','amount':state['budget'],'at':dt.datetime.now(TZ).isoformat()})
    elif action=='small-cream': state['small_cream']=True; state['approvals'].pop('pack',None)
    elif action=='restore': state['overrides'].pop(value,None)
    elif action=='add':
        pid=str(value)
        if any(r['product_id']==pid and r['units']>0 for r in before['rows']) or any(e['product_id']==pid for e in state['extra']): raise KitchenError('That product is already added.')
        state['extra'].append({'product_id':pid,'units':1})
    elif action=='undo-wedding':
        state['wedding']=state.pop('previous_wedding',None);state['overrides']={};state['approvals']={};state.pop('previous_rows',None)
    elif action=='place':
        # Fresh supply and prices at commitment. No buyer-supplied price or OK is trusted.
        order=build(state,fresh=True)
        if not order['can_place']: return {**order,'token':seal(state),'place_error':'The order changed. Check the highlighted products before placing.'}
        oid='VO-47-'+digest([state['created'],[(r['product_id'],r['units'],r['unit_price']) for r in order['rows']]])[:6].upper()
        order['confirmation']={'order_number':oid,'at':dt.datetime.now(TZ).isoformat(),'demo':True,
                               'notice':'Demo account. Nothing ships. Valio’s Junction API has no order endpoint.'}
        state['events'].append({'action':'Demo order confirmed','order':oid,'total':order['total'],'at':dt.datetime.now(TZ).isoformat()})
        order['token']=seal(state);return order
    else: raise KitchenError('That change is not supported.')
    return response(state)

def apply_menu(token, parsed):
    state=unseal(token)
    if parsed.get('status')!='readable' or not parsed.get('dishes'): raise KitchenError("Couldn't read a complete menu. Review what we saw and try another photo.")
    previous=build(state)
    state['previous_rows']=[r for r in previous['rows'] if r['units']>0]
    state['previous_wedding']=state.get('wedding')
    state['wedding']={'date':'2026-11-21','covers':parsed['covers'],'dishes':parsed['dishes'],
                      'from_photo':parsed.get('source')=='photo','transcript':parsed.get('transcript',''),
                      'read':parsed.get('read',[])}
    state['overrides']={}
    state['events'].append({'action':'Read photo' if parsed.get('source')=='photo' else 'Chef request',
                            'text':parsed.get('transcript',''),'read':parsed.get('read',[]),'at':dt.datetime.now(TZ).isoformat()})
    return response(state)
