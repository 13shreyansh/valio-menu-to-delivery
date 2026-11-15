from chefagent import kitchen as k,portal_fixtures as f
s=k.initial_state();s['budget']=1500
for stage in ['base','wedding']:
 if stage=='wedding':s['wedding']={'date':'2026-11-21','covers':120,'dishes':[{'recipe':'soup','covers':120},{'recipe':'whitefish','covers':120},{'recipe':'tart','covers':120}]}
 o=k.build(s,context=f)
 print(stage,'rows',len(o['rows']),'total',o['total'],'checks',[(c['id'],c['text']) for c in o['checks']])
