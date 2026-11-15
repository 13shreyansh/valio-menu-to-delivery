"""Run a local command with project credentials held only in process memory."""
import json, os, subprocess, sys
from pathlib import Path
import httpx
p=Path.home()/'Library/Application Support/com.vercel.cli/auth.json'
auth=json.loads(p.read_text())
h={'Authorization':'Bearer '+auth['token']}
url='https://api.vercel.com/v9/projects/valio-menu-to-delivery/env?decrypt=true&teamId=team_SjINqXczvI3i0JpBv7JRMqQN'
r=httpx.get(url,headers=h); r.raise_for_status()
env=os.environ.copy()
for e in r.json()['envs']:
 if 'production' in e.get('target',[]):
  one=httpx.get('https://api.vercel.com/v1/projects/valio-menu-to-delivery/env/'+e['id'],params={'teamId':'team_SjINqXczvI3i0JpBv7JRMqQN'},headers=h);one.raise_for_status()
  env[e['key']]=one.json()['value']
if sys.argv[1:]==['--names']: print(', '.join(sorted(k for k in env if k in [e['key'] for e in r.json()['envs']])))
else: sys.exit(subprocess.call(sys.argv[1:],env=env))
