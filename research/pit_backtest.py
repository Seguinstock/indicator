import json, math, random, time, sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd
import yfinance as yf
import pitindex

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'engine'))
import scanner
from validate_potential import potential_score

DATES=['2022-01-03','2022-07-01','2023-01-03','2023-07-03','2024-01-02','2024-07-01','2025-01-02','2025-07-01']
TOP_N=30
HORIZON_DAYS=365
RANDOM_DRAWS=500
BATCH=100
SEED=24061980


def restrict_factory(asof):
    def restrict(h):
        h=h.dropna(subset=['Close']).copy()
        if h.empty:return h
        idx=pd.to_datetime(h.index)
        if getattr(idx,'tz',None):idx=idx.tz_localize(None)
        return h.loc[(idx<=asof)&(idx>=asof-pd.Timedelta(days=scanner.HISTORY_DAYS))].copy()
    return restrict


def calc_asof(ticker,h,cfg,asof):
    old=scanner.restrict_v14_history
    scanner.restrict_v14_history=restrict_factory(asof)
    try:
        return scanner.calc({'symbol':ticker,'market':'XNYS','country':'US'},h,cfg)
    finally:
        scanner.restrict_v14_history=old


def forward_stats(h,asof,end,entry):
    idx=pd.to_datetime(h.index)
    if getattr(idx,'tz',None):idx=idx.tz_localize(None)
    f=h.loc[(idx>asof)&(idx<=end)].dropna(subset=['Close'])
    if f.empty:return None
    last=pd.Timestamp(f.index[-1])
    if last.tzinfo:last=last.tz_localize(None)
    return {
        'return_pct':(float(f['Close'].iloc[-1])/entry-1)*100,
        'max_upside_pct':(float(f['High'].max())/entry-1)*100,
        'max_drawdown_pct':(float(f['Low'].min())/entry-1)*100,
        'ended_early':bool(last<end-pd.Timedelta(days=10)),
    }


def summarize(rows):
    if not rows:return None
    r=np.array([x['return_pct'] for x in rows],float)
    u=np.array([x['max_upside_pct'] for x in rows],float)
    d=np.array([x['max_drawdown_pct'] for x in rows],float)
    return {
        'n':len(rows),'avg_final_pct':round(float(r.mean()),2),'median_final_pct':round(float(np.median(r)),2),
        'win_rate_pct':round(float((r>0).mean()*100),1),'avg_peak_pct':round(float(u.mean()),2),
        'avg_drawdown_pct':round(float(d.mean()),2),'peak_50_pct':round(float((u>=50).mean()*100),1),
        'peak_80_pct':round(float((u>=80).mean()*100),1),'peak_100_pct':round(float((u>=100).mean()*100),1),
        'peak_200_pct':round(float((u>=200).mean()*100),1),'peak_lt10_pct':round(float((u<10).mean()*100),1),
        'ended_early_pct':round(float(np.mean([x['ended_early'] for x in rows])*100),1),
    }


def random_benchmark(rows,seed):
    if len(rows)<TOP_N:return None
    rng=random.Random(seed); samples=[]
    for _ in range(RANDOM_DRAWS):samples.append(summarize(rng.sample(rows,TOP_N)))
    out={}
    for k in ['avg_final_pct','avg_peak_pct','avg_drawdown_pct','peak_50_pct','peak_80_pct','peak_100_pct','peak_200_pct','peak_lt10_pct']:
        v=np.array([x[k] for x in samples],float)
        out[k]={'mean':round(float(v.mean()),2),'p05':round(float(np.quantile(v,.05)),2),'p50':round(float(np.quantile(v,.5)),2),'p95':round(float(np.quantile(v,.95)),2)}
    return out


def run_date(ds,cfg):
    asof=pd.Timestamp(ds); end=asof+pd.Timedelta(days=HORIZON_DAYS)
    members=pitindex.get_constituents(ds,index='sp1500')
    tickers=list(dict.fromkeys(str(t).strip().replace('.','-') for t in members['ticker'].tolist()))
    tested=[]; failed=[]
    start=(asof-pd.Timedelta(days=650)).strftime('%Y-%m-%d'); dlend=(end+pd.Timedelta(days=1)).strftime('%Y-%m-%d')
    for i in range(0,len(tickers),BATCH):
        batch=tickers[i:i+BATCH]
        try:raw=yf.download(batch,start=start,end=dlend,group_by='ticker',auto_adjust=True,threads=True,progress=False,timeout=30)
        except Exception:
            failed.extend(batch); continue
        for ticker in batch:
            try:
                h=raw[ticker] if len(batch)>1 else raw
                x=calc_asof(ticker,h,cfg,asof)
                hist=restrict_factory(asof)(h)
                if not x or hist.empty:
                    failed.append(ticker); continue
                f=forward_stats(h,asof,end,float(hist['Close'].iloc[-1]))
                if not f:
                    failed.append(ticker); continue
                row={k:x.get(k) for k in ['symbol','score','rsi','rvol','trend','volatility_pct','support_distance_pct']}
                row['old_score']=float(x.get('score') or 0)
                row['potential_score']=float(potential_score(x))
                row.update(f)
                tested.append(row)
            except Exception:
                failed.append(ticker)
        time.sleep(.35)
    old_top=sorted(tested,key=lambda x:x['old_score'],reverse=True)[:TOP_N]
    new_top=sorted(tested,key=lambda x:x['potential_score'],reverse=True)[:TOP_N]
    return {
        'asof':ds,'end':end.strftime('%Y-%m-%d'),'pit_universe':len(tickers),'tested':len(tested),'failed':len(set(failed)),
        'coverage_pct':round(len(tested)/len(tickers)*100,1) if tickers else 0,
        'old_top30':summarize(old_top),'potential_top30':summarize(new_top),
        'random_top30':random_benchmark(tested,SEED+int(asof.strftime('%Y%m%d'))),'whole_universe':summarize(tested),
        'old_symbols':[x['symbol'] for x in old_top],'potential_symbols':[x['symbol'] for x in new_top],
        'failed_sample':sorted(set(failed))[:60],
    }


def main():
    cfg=json.loads((ROOT/'config/parameters.json').read_text(encoding='utf-8'))
    results=[]
    for ds in DATES:
        print('RUN',ds,flush=True)
        try:
            r=run_date(ds,cfg);results.append(r);print(ds,r['coverage_pct'],r['potential_top30'],flush=True)
        except Exception as e:
            results.append({'asof':ds,'error':repr(e)});print('ERROR',ds,repr(e),flush=True)
    good=[r for r in results if 'error' not in r]
    out={'generated':datetime.now(timezone.utc).isoformat(),'protocol':{
        'universe':'S&P 1500 point-in-time reconstructed with pitindex','dates':DATES,'top_n':TOP_N,'horizon_days':HORIZON_DAYS,'random_draws':RANDOM_DRAWS,
        'potential_formula':'50% volatility, 20% trend, 15% RVOL, 10% RSI around 40, 5% support proximity',
        'limitations':['Survivorship-reduced, not perfectly survivorship-free.','Yahoo may lack price history for some delisted/renamed securities; failures and coverage are reported.','S&P 1500 membership itself excludes many tiny/speculative issuers and is not a full US-listed-stock universe.']},'results':results}
    (ROOT/'data/pit_validation.json').write_text(json.dumps(out,ensure_ascii=False,indent=2),encoding='utf-8')
    lines=['# Point-in-time validation','','| Date | Coverage | New final | New peak | >=50 | >=80 | >=100 | >=200 | <10 | Old final | Random final |','|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|']
    for r in good:
        n=r['potential_top30'];o=r['old_top30'];rb=r['random_top30']['avg_final_pct']['mean']
        lines.append(f"| {r['asof']} | {r['coverage_pct']}% | {n['avg_final_pct']}% | {n['avg_peak_pct']}% | {n['peak_50_pct']}% | {n['peak_80_pct']}% | {n['peak_100_pct']}% | {n['peak_200_pct']}% | {n['peak_lt10_pct']}% | {o['avg_final_pct']}% | {rb}% |")
    lines+=['','## Limitations','','- Point-in-time S&P 1500 reduces survivorship bias but does not eliminate it.','- Missing Yahoo histories for delisted/renamed names are explicitly counted as failures.','- No production scoring parameters are modified by this research script.']
    (ROOT/'data/pit_validation.md').write_text('\n'.join(lines),encoding='utf-8')

if __name__=='__main__':main()
