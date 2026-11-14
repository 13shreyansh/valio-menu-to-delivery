"""Archive redundant, untouched prepared-week pointers; preserve every document."""
import json,sys,uuid
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from chefagent import portal as p
from chefagent.account_store import Store
book,etag=p.ledger()
plain=[d for d in book.get('drafts',[]) if d['status']=='Draft' and d['placed_by']=='Sanna Virtanen' and not d.get('request')]
redundant=[d for d in plain[1:] if d['total']==plain[0]['total']]
result={'redundant_untouched_drafts_archived':len(redundant),'preserved_orders':len(book['orders'])}
if redundant:
    archive=Store(namespace='archives/job03-drafts-'+uuid.uuid4().hex)
    archive.put('ledger',book)
    ids={d['draft_id'] for d in redundant}
    book['drafts']=[d for d in book['drafts'] if d['draft_id'] not in ids]
    Store().put('ledger',book,etag)
    result['archive']=archive.namespace
Path('artifacts/job03-draft-cleanup.json').write_text(json.dumps(result,indent=2))
print(json.dumps(result))
