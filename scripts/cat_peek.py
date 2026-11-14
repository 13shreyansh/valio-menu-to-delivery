import sys,collections;sys.path.insert(0,'.')
from chefagent.catalog import load
c=load()
for w in sys.argv[1:]:
    cc=collections.defaultdict(list)
    for p in c.food:
        t=(' '+p['name']+' | '+p['name_fi']+' ').lower()
        if w.lower() in t: cc[p['category']].append(p['name'][:38])
    print('##',w, ' '.join(f"{k}:{len(v)}[{'; '.join(v[:3])}]" for k,v in sorted(cc.items(),key=lambda kv:-len(kv[1]))[:6]))
