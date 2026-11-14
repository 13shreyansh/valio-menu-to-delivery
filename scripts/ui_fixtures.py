"""Synthetic €1 quotes for DOM tests only. Not product data and never served."""
import json,os,sys
from pathlib import Path
Path('artifacts').mkdir(exist_ok=True)
sys.path.insert(0,'.')
from tests.conftest import Catalog,Supplier
from chefagent import kitchen as k
os.environ['KITCHEN_SIGNING_KEY']='isolated-unit-test-key'
k.load=Catalog;k.ValioAPI=Supplier
s=k.initial_state();initial=k.response(s)
s['budget']=150
s['wedding']={'date':'2026-11-21','covers':120,'dishes':[{'recipe':'salmon','covers':120},{'recipe':'tart','covers':120}],'transcript':'Wedding Saturday, 120 guests, salmon and lemon tart'}
wedding=k.response(s);acks={};approved=wedding
for check in ['swap','pack','budget']:
 if check not in [c['id'] for c in approved['checks']]:continue
 approved=k.act(approved['token'],'approve',check);acks[check]=approved
cream=next(r for r in approved['rows'] if r['id']=='2026-11-20-cream')
reopened=k.act(approved['token'],'quantity',{'id':cream['id'],'units':cream['units']+1})
photo={'status':'readable','transcript':'Saturday wedding 120 guests, whitefish 120, lemon tart 120, cheese board 140', 'covers':120,'dishes':[{'recipe':'whitefish','covers':120},{'recipe':'tart','covers':120},{'recipe':'cheeseboard','covers':140}], 'read':[{'word':'Paistettu siika 120','box':[200,100,300,800],'uncertain':False}], 'source':'photo','uncertain':[]}
final=k.apply_menu(approved['token'],photo)
final_approved=final
for check in final['checks']:
 if not check['approved']: final_approved=k.act(final_approved['token'],'approve',check['id'])
confirmed=k.act(final_approved['token'],'place')
json.dump({'initial':initial,'wedding':wedding,'acks':acks,'approved':approved,'reopened':reopened,'photo':photo,'final':final,'final_approved':final_approved,'confirmed':confirmed},open('artifacts/ui-local.json','w'))
