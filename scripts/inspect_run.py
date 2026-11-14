import json,sys,glob
for f in sorted(glob.glob(f"eval/runs/{sys.argv[1]}/*.score.json")):
    s=json.load(open(f)); o=json.load(open(f.replace('.score','.order')))
    print('=====',s['case'])
    for it in s['items']:
        bad=[c for c in it['components'] if c['ess'] and not c['covered']]
        print(f" {'OK ' if it['cookable'] else 'NO '} {it['text'][:50]:50s}", ' | '.join(f"{c['accept'][0]}:{(c['best'] or {}).get('ratio')}" for c in it['components'] if c['ess']))
        for c in bad: print('     MISSING',c['accept'],c['best'])
        for v in it['violations']: print('     VIOL',v)
    for g in o['gaps']: print('  GAP',g['ingredient'],g['why'][:150])
    for d in o['deliveries']:
        for l in d['lines']:
            print(f"   {l['delivery_date']} {l['name'][:45]:45s} {l['units']:g}{l['sales_unit']} need {l['need_kg']}kg ord {l['ordered_kg']}kg €{l['line_total']} [{l['ingredient']}] {'SUB' if l['substitution'] else ''} {'HOLD' if l['needs_approval'] else ''}")
