import hashlib, json, os, runpy, time
from pathlib import Path
import pandas as pd
import yfinance as yf

ROOT=Path(__file__).resolve().parents[1]
CACHE=ROOT/'.cache'/'rs3y'; CACHE.mkdir(parents=True,exist_ok=True)
TARGET=ROOT/'engine'/'continuous_rs_3y_protected.py'
RULES=['fixed','armed10_5','armed15_8','surge10_5_tech','surge15_6_tech','surge20_8_tech']
ORIG=yf.download
stats={'hits':0,'network':0,'retries':0}

def symbols(args,kwargs):
    x=args[0] if args else kwargs.get('tickers',[])
    if isinstance(x,str): return [s for s in x.replace(',',' ').split() if s]
    return list(x or [])

def quality(df,syms):
    if df is None or df.empty: return 0.0
    if len(syms)<=1:
        try:
            if isinstance(df.columns,pd.MultiIndex): return 1.0 if df.notna().any().any() else 0.0
            return 1.0 if 'Close' in df and df['Close'].notna().any() else 0.0
        except Exception: return 0.0
    if not isinstance(df.columns,pd.MultiIndex): return 0.0
    top=set(map(str,df.columns.get_level_values(0))); good=0
    for s in syms:
        if s in top:
            try:
                if 'Close' in df[s] and df[s]['Close'].notna().any(): good+=1
            except Exception: pass
    return good/max(len(syms),1)

def cached_download(*args,**kwargs):
    key=hashlib.sha256(repr((args,sorted(kwargs.items()))).encode()).hexdigest()
    p=CACHE/(key+'.pkl')
    if p.exists():
        stats['hits']+=1; return pd.read_pickle(p)
    syms=symbols(args,kwargs); best=None; bq=-1.0
    for n in range(5):
        if n:
            stats['retries']+=1; time.sleep(min(15*n,60))
        kw=dict(kwargs)
        if n: kw['threads']=False
        try:
            stats['network']+=1; df=ORIG(*args,**kw)
        except Exception:
            continue
        q=quality(df,syms)
        if q>bq: best,bq=df,q
        need=1.0 if len(syms)<=1 else 0.70
        if q>=need: break
    if best is None or best.empty: raise RuntimeError('Yahoo download failed')
    need=1.0 if len(syms)<=1 else 0.70
    if bq<need: raise RuntimeError(f'Yahoo completeness too low: {bq:.1%}')
    best.to_pickle(p); time.sleep(1.0); return best

yf.download=cached_download

for rule in RULES:
    print('=====',rule,'=====')
    os.environ['SELL_RULE']=rule
    runpy.run_path(str(TARGET),run_name='__main__')
    p=ROOT/'data'/f'backtest_relative_strength_continuous_3y_{rule}.json'
    d=json.loads(p.read_text())
    hs=d.get('benchmark_top100_sp500',{}).get('holdings',[])
    flags=[{'symbol':h.get('symbol'),'return_pct':h.get('return_pct'),'entry_price':h.get('entry_price'),'final_price':h.get('final_price')} for h in hs if isinstance(h.get('return_pct'),(int,float)) and abs(h['return_pct'])>=300]
    d['price_audit']={'extreme_return_threshold_pct':300,'extreme_benchmark_returns':flags,'wdc_note':'WDC had the 2025 SanDisk spin-off; adjusted history can embed corporate-action adjustments.'}
    d['download_audit']={'shared_cache_enabled':True,**stats}
    p.write_text(json.dumps(d,ensure_ascii=False,indent=2))
print(json.dumps({'completed':RULES,**stats},indent=2))
