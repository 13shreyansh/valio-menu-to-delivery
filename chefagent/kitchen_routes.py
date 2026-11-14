import json
from pathlib import Path
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from . import kitchen as k
from .kitchen_intake import understand, validate_reading
from .kitchen_fixtures import WEDDING_TEXT
router=APIRouter(prefix='/api/sheet')

def sheet_state(body):
    state=k.unseal(body.get('token',''))
    # Late reads contribute their signed receipt to the current sheet, never old quantities or OKs.
    for token in body.get('photo_receipts',[])[:20]:
        receipt=k.unseal(token);call=receipt.get('call')
        if call and call.get('purpose')=='whiteboard understanding' and not any(c.get('id')==call.get('id') for c in state['calls']):
            state['calls'].append(call)
    return state


@router.get('')
def sheet(): return k.response(k.initial_state())

@router.post('/change')
async def change(req:Request):
    b=await req.json()
    return k.act(k.seal(sheet_state(b)),b.get('action'),b.get('value'))

@router.post('/tell')
async def tell(req:Request):
    b=await req.json(); state=sheet_state(b)
    source='audio' if b.get('media') else 'text'
    reading=understand(text=b.get('text') if source=='text' else None,media=b.get('media'),source=source)
    for token in b.get('listened_tokens',[])[:4]:
        listened=k.unseal(token)
        if listened.get('call',{}).get('purpose')=='live speech reading': state['calls'].append(listened['call'])
    state['calls'].append({'method':'POST','source':'Gemini','purpose':source+' understanding','status':200})
    if reading['status']!='readable': return {'reading':reading,'token':k.seal(state),'calls':state['calls']}
    out=k.apply_menu(k.seal(state),reading);out['reading']=reading;return out

@router.post('/photo')
async def photo(req:Request):
    b=await req.json();state=sheet_state(b)
    reading=understand(media=b.get('media'),source='photo')
    call={'id':str(__import__('time').time_ns()),'method':'POST','source':'Gemini','purpose':'whiteboard understanding','status':200}
    state['calls'].append(call)
    return {'reading':reading,'token':k.seal(state),'calls':state['calls'],'call':call,'read_token':k.seal({'created':__import__('time').time(),'reading':reading,'call':call})}

@router.post('/photo/apply')
async def photo_apply(req:Request):
    b=await req.json(); receipt=k.unseal(b.get('read_token','')); verified=receipt['reading']
    can_correct=(verified['status']=='uncertain' and verified.get('dishes') and isinstance(verified.get('covers'),int) and verified.get('transcript','').strip())
    if verified['status']!='readable' and not (can_correct and b.get('confirmed') is True): raise k.KitchenError("Couldn't read the full menu. Try a clearer photo before updating the order.")
    # Chef may correct the visible portions, but cannot change an unreadable result to readable.
    reading=validate_reading(b.get('reading') or verified,'photo')
    if reading['status']!='readable': raise k.KitchenError('Check the menu words and portion counts first.')
    state=sheet_state(b)
    call=receipt.get('call')
    if call and not any(c.get('id')==call.get('id') for c in state['calls']):state['calls'].append(call)
    state['events'].append({'action':'Photo words checked by chef' if b.get('confirmed') else 'Photo reviewed','at':__import__('datetime').datetime.now(k.TZ).isoformat()})
    return k.apply_menu(k.seal(state),reading)

@router.get('/story-reading')
def story_reading():
    p=Path(__file__).resolve().parent.parent/'public'/'story-readings.json'
    if not p.exists(): return {'ready':False}
    data=json.loads(p.read_text())
    # Only interpretations checked against actual Gemini output are recorded here.
    reading=data['wedding']; photo=data['photo']
    return {'ready':True,'reading':reading,'photo':photo,
            'read_token':k.seal({'created':__import__('time').time(),'reading':photo}),
            'wedding_token':k.seal({'created':__import__('time').time(),'reading':reading})}

@router.post('/story-wedding')
async def story_wedding(req:Request):
    b=await req.json(); reading=k.unseal(b.get('wedding_token',''))['reading']
    if reading.get('status')!='readable': raise k.KitchenError('Read the wedding menu first.')
    state=k.unseal(b.get('token','')); state['events'].append({'action':'Play the story','note':'Recorded Gemini reading; fresh Valio quotes and all controls still run.'})
    return k.apply_menu(k.seal(state),reading)

@router.post('/listen')
async def listen(req:Request):
    b=await req.json(); k.unseal(b.get('token',''))
    reading=understand(media=b.get('media'),source='audio')
    call={'method':'POST','source':'Gemini','purpose':'live speech reading','status':200}
    return {'transcript':reading.get('transcript',''), 'call_token':k.seal({'created':__import__('time').time(),'call':call})}
