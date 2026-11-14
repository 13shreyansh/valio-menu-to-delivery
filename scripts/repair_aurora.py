"""One-time, reversible Hotel Aurora account repair (Job 03).

All quantities come from the kitchen recipes/bookings and all prices from Valio.
Each past weekly order is prepared, approved and placed by the SAME portal engine.
The historical kitchen dates are authored sample-account lifecycle data; supplier
quotes remain their actual current dates, never presented as historical API calls.
The polluted legacy namespace is preserved. No document is deleted or overwritten.
"""
import copy, datetime as dt, json, sys, uuid
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from chefagent import portal as p
from chefagent.account_store import Store
from chefagent.account_scope import kitchen_scope


def delivered_copy(order, week_start):
    out=copy.deepcopy(order)
    shift=dt.date.fromisoformat(week_start)-dt.date(2026,11,16)
    def historical_day(day):return (dt.date.fromisoformat(day)+shift).isoformat()
    out['placed_at']=(dt.datetime.fromisoformat(week_start+'T15:00:00+02:00')-dt.timedelta(days=1)).isoformat()
    out.update(historical=True,price_checked_at=order['quote_at'],week=dt.date.fromisoformat(week_start).isocalendar().week)
    out['history_provenance']={
        'flow':'portal.new_draft -> portal.change(approve) -> portal.place',
        'lifecycle':'Authored past kitchen delivery dates; current Valio quotes retained in evidence',
        'quoted_deliveries':[d['date'] for d in order['deliveries']],
    }
    for row in out['rows']:row['delivery']=historical_day(row['delivery'])
    for delivery in out['deliveries']:
        delivery['date']=historical_day(delivery['date'])
        # A past kitchen delivery record cannot assert a historical supplier cutoff.
        delivery['cutoff']=None
        for row in delivery['rows']:row['delivery']=delivery['date']
    for service in out['services']:service['date']=historical_day(service['date'])
    return out


def repair():
    target=Store()
    done,_=target.get('job03-repair')
    if done:return done
    existing,existing_etag=target.get('ledger')
    if existing and existing['orders'] and '--reset-unpublished' not in sys.argv:raise RuntimeError('Fresh active namespace expected; refusing to replace real orders')
    old=Store(namespace='aurora')
    legacy,legacy_etag=old.get('ledger')
    archive='archives/job03-'+uuid.uuid4().hex
    archive_store=Store(namespace=archive)
    archive_store.put('manifest',{'legacy_namespace':'aurora','active_namespace':target.namespace,'at':p.now(),'legacy_ledger_etag':legacy_etag,'reason':'Automated tests shared Hotel Aurora storage; original namespace remains intact'})
    archive_store.put('ledger',legacy or {'orders':[],'events':[],'drafts':[]})
    if existing:
        archive_store.put('unfinished-repair-ledger',existing)
        target.put('ledger',{'orders':[],'events':[],'drafts':[]},existing_etag)
    for key in ['rules','history']:
        value,_=old.get(key)
        if value:archive_store.put(key,value)
    # Different account-owned cover counts for the three past service weeks.
    # Sales-pack rounding and Valio customer prices determine each order total.
    created=[]
    for week_start,factor in [('2026-10-26',0.84),('2026-11-02',0.94),('2026-11-09',1.04)]:
        services=copy.deepcopy(p.f.BASE_SERVICES)
        for service in services:service['covers']=round(service['covers']*factor)
        o=p.new_draft(services=services)
        for check in o['checks']:
            if not check['approved']:
                if not check['can_approve']:raise RuntimeError('Historical order cannot pass the current rules')
                o=p.change(o['draft_id'],'approve',check['id'])
        placed=p.place(o['draft_id'])
        past=delivered_copy(placed,week_start)
        key='completed-history/'+placed['draft_id']
        target.put(key,past)
        book,etag=p.ledger()
        entry=next(e for e in book['orders'] if e['draft_id']==placed['draft_id'])
        entry.update(snapshot_key=key,placed_at=past['placed_at'],status='Delivered',week=past['week'],historical=True,price_checked_at=past['price_checked_at'],rows=past['rows'],deliveries=past['deliveries'])
        for event in book['events']:
            if event['id']==entry['order_number']:event['at']=past['placed_at']
        target.put('ledger',book,etag)
        created.append({k:entry[k] for k in ['order_number','placed_at','total','products','week']})
    result={'at':p.now(),'archive':archive,'legacy_orders_archived':len((legacy or {}).get('orders',[])), 'active_orders':created,'note':'Sample kitchen history created through actual order engine, valued with current real Valio quotes. Historical delivery dates are kitchen records, not historical supplier responses.'}
    target.put('job03-repair',result)
    return result

if __name__=='__main__':
    with kitchen_scope('aurora'):result=repair()
    Path('artifacts').mkdir(exist_ok=True)
    Path('artifacts/job03-history-repair.json').write_text(json.dumps(result,indent=2))
    print(json.dumps(result,indent=2))
