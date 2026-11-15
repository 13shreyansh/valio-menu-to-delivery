from chefagent.account_store import Store
s=Store(); doc,v=s.get('storage-health');print('Read:',bool(doc))
v=s.put('storage-health',{'checked':__import__('time').time()},v)
d,w=s.get('storage-health');print('Durable private read/write:',bool(d),'version present:',bool(w))
