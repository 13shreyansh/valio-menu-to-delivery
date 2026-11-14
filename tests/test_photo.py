import pytest
from fastapi.testclient import TestClient
from api.index import app
from chefagent.kitchen_intake import validate_reading
from chefagent import kitchen as k

@pytest.mark.parametrize('raw',[{}, {'status':'readable','transcript':'','covers':120,'dishes':[{'recipe':'salmon','covers':120}]},
 {'status':'readable','transcript':'???','covers':120,'dishes':[{'recipe':'salmon','covers':120}],'uncertain':['fish?']},
 {'status':'readable','transcript':'a board','covers':None,'dishes':[{'recipe':'salmon','covers':120}]},
 {'status':'readable','transcript':'a board','covers':120,'dishes':[{'recipe':'unknown','covers':120}]},
 {'status':'readable','transcript':'a board','covers':120,'dishes':[{'recipe':'salmon','covers':-1}]},
 {'status':'readable','transcript':'a board','covers':120,'dishes':[{'recipe':'salmon','covers':120}],'read':[{'word':'fish','uncertain':True}]}])
def test_blank_garbled_uncertain_cannot_change_order(raw):
    r=validate_reading(raw,'photo');assert r['status']!='readable'
    with pytest.raises(k.KitchenError):k.apply_menu(k.seal(k.initial_state()),r)

def test_unreadable_photo_cannot_be_relabelled(wedding_state):
    client=TestClient(app)
    bad=k.seal({'created':__import__('time').time(),'reading':{'status':'unreadable'}})
    forged={'status':'readable','transcript':'wedding','covers':120,'dishes':[{'recipe':'salmon','covers':120}]}
    r=client.post('/api/sheet/photo/apply',json={'token':k.seal(wedding_state),'read_token':bad,'reading':forged})
    assert r.status_code==422 and "Couldn't read" in r.json()['error']

def test_complete_final_menu_replaces_only_wedding(wedding_state):
    raw={'status':'readable','transcript':'Final wedding menu 120 guests','covers':120,
         'dishes':[{'recipe':'whitefish','covers':120},{'recipe':'tart','covers':120},{'recipe':'cheeseboard','covers':140}]}
    o=k.apply_menu(k.seal(wedding_state),validate_reading(raw,'photo'))
    assert any(s['recipe']=='soup' and not s.get('wedding') for s in o['services'])
    assert [s['recipe'] for s in o['services'] if s.get('wedding')]==['whitefish','tart','cheeseboard']
    assert next(r for r in o['rows'] if r['role']=='whitefish')['units']==18

def test_legible_uncertain_photo_requires_explicit_correction(wedding_state):
    client=TestClient(app)
    reading={'status':'uncertain','transcript':'Saturday 120 guests whitefish?','covers':120,
             'dishes':[{'recipe':'whitefish','covers':120}],'read':[],'uncertain':['whitefish?']}
    stamp=k.seal({'created':__import__('time').time(),'reading':reading})
    corrected={**reading,'status':'readable','uncertain':[]}
    body={'token':k.seal(wedding_state),'read_token':stamp,'reading':corrected}
    assert client.post('/api/sheet/photo/apply',json=body).status_code==422
    body['confirmed']=True
    assert client.post('/api/sheet/photo/apply',json=body).status_code==200

def test_late_photo_receipt_merges_into_latest_sheet_without_old_approvals(wedding_state):
    from chefagent.kitchen_routes import sheet_state
    call={'id':'photo-receipt-test','purpose':'whiteboard understanding','source':'Gemini'}
    receipt=k.seal({'created':__import__('time').time(),'reading':{'status':'unreadable'},'call':call})
    wedding_state['budget']=1234
    state=sheet_state({'token':k.seal(wedding_state),'photo_receipts':[receipt,receipt]})
    assert state['budget']==1234 and not state['approvals']
    assert state['calls']==[call]
