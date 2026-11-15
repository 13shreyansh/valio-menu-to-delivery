"""Create entry-owned private storage; credentials never leave process memory."""
import json
from pathlib import Path
import httpx
key=json.loads((Path.home()/'Library/Application Support/com.vercel.cli/auth.json').read_text())['token']
h={'Authorization':'Bearer '+key}; base='https://api.vercel.com'; team='team_SjINqXczvI3i0JpBv7JRMqQN'; project='prj_ZnsmA7iHN4kCKjIw4qIb2tIx4liN'
r=httpx.post(base+'/v1/storage/stores/blob',params={'teamId':team},headers=h,json={'name':'valio-aurora-account','access':'private','region':'arn1','projectId':project},timeout=60)
print('Create private storage:',r.status_code)
if r.is_success:
 data=r.json(); print('Response fields:',list(data)); print('Store:', data.get('store',{}).get('id') or data.get('id'))
 # No response values are written or logged.
else: print('Error:',r.json().get('error',{}).get('message','unknown'))
