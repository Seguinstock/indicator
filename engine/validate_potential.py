import json, os, subprocess, sys
from pathlib import Path
from datetime import datetime, timezone

ROOT=Path(__file__).resolve().parents[1]
BACKTEST=ROOT/'engine/backtest.py'
OUT=ROOT/'data/backtest_validation.json'
CURRENT=ROOT/'data/backtest.json'

WINDOWS=[
    ('2023-02-14','2024-02-14'),
    ('2023-08-21','2024-08-21'),
    ('2024-01-11','2025-01-11'),
    ('2024-07-23','2025-07-23'),
    ('2025-03-17','2026-03-17'),
]

def clip(x,a,b): return max(a,min(b,x))

def potential_score(r):
    vol=clip((float(r.get('volatility_pct') or 0)-15)/55,0,1)*50
    t=float(r.get('trend') or 0)
    tmap={-2:0,-1:.1,-.5:.25,0:.5,.5:.65,1:.8,2:1}
    trend=tmap.get(t,.5)*20
    rvol=clip((float(r.get('rvol') or 0)-.5)/1.5,0,1)*15
    rsi=float(r.get('rsi') or 50)
    rsiq=clip(1-abs(rsi-40)/20,0,1)*10
    d=r.get('support_distance_pct')
    support=.5 if d is None else clip((10-float(d))/10,0,1)
    return round(vol+trend+rvol+rsiq+support*5,2)

def metrics(rows, key, n=30):
    a=sorted(rows,key=lambda r:float(r.get(key) or -999),reverse=True)[:n]
    ups=[float(r.get('max_upside_pct') or 0) for r in a]
    rets=[float(r.get('return_pct') or 0) for r in a]
    return {
      'n':len(a),
      'avg_peak_pct':round(sum(ups)/len(ups),2),
      'avg_final_pct':round(sum(rets)/len(rets),2),
      'peak_50':sum(x>=50 for x in ups),
      'peak_80':sum(x>=80 for x in ups),
      'peak_100':sum(x>=100 for x in ups),
      'peak_200':sum(x>=200 for x in ups),
      'peak_lt_10':sum(x<10 for x in ups),
      'symbols':[r['symbol'] for r in a]
    }

def run_window(asof,end):
    env=os.environ.copy();env['BACKTEST_ASOF']=asof;env['BACKTEST_END']=end
    subprocess.run([sys.executable,str(BACKTEST)],cwd=ROOT,env=env,check=True)
    d=json.loads(CURRENT.read_text(encoding='utf-8'))
    rows=d.get('all_rows',[])
    for r in rows:r['potential_score']=potential_score(r)
    return {
      'asof':asof,'end':end,'tested':d.get('tested'),
      'current_top30':metrics(rows,'score',30),
      'potential_top30':metrics(rows,'potential_score',30),
      'current_top100':metrics(rows,'score',100),
      'potential_top100':metrics(rows,'potential_score',100),
    }

def aggregate(windows,label):
    keys=['avg_peak_pct','avg_final_pct','peak_50','peak_80','peak_100','peak_200','peak_lt_10']
    out={}
    for k in keys:
        vals=[w[label][k] for w in windows]
        out[k]=round(sum(vals)/len(vals),2)
    return out

def main():
    original=CURRENT.read_text(encoding='utf-8') if CURRENT.exists() else None
    results=[]
    try:
        for a,e in WINDOWS:results.append(run_window(a,e))
    finally:
        if original is not None:CURRENT.write_text(original,encoding='utf-8')
    out={
      'generated':datetime.now(timezone.utc).isoformat(),
      'windows':results,
      'aggregate':{
        'current_top30':aggregate(results,'current_top30'),
        'potential_top30':aggregate(results,'potential_top30'),
        'current_top100':aggregate(results,'current_top100'),
        'potential_top100':aggregate(results,'potential_top100'),
      },
      'prototype':'50% volatilité, 20% tendance, 15% RVOL, 10% RSI autour de 40, 5% proximité zone de rebond'
    }
    OUT.write_text(json.dumps(out,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(out['aggregate'],ensure_ascii=False,indent=2))

if __name__=='__main__':main()
