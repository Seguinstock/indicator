import json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
d=json.loads((ROOT/'data/backtest_validation.json').read_text(encoding='utf-8'))
out={'generated':d.get('generated'),'prototype':d.get('prototype'),'aggregate':d.get('aggregate'),'windows':[]}
for w in d.get('windows',[]):
    x={'asof':w['asof'],'end':w['end'],'tested':w.get('tested')}
    for k in ['current_top30','potential_top30','current_top100','potential_top100']:
        x[k]={a:b for a,b in w[k].items() if a!='symbols'}
    out['windows'].append(x)
(ROOT/'data/backtest_validation_summary.json').write_text(json.dumps(out,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps(out,ensure_ascii=False,indent=2))
