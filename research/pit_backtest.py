import json, random, time, sys
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
BATCH=50
SEED=24061980
RETRIES=3


def restrict_factory(asof):
    def restrict(h):
        h=h.dropna(subset=['Close']).copy()
        if h.empty:return h
        idx=pd.to_datetime(h.index)
        if getattr(idx,'tz',None):idx=idx.tz_localize(None)
        mask=(idx<=asof)&(idx>=asof-pd.Timedelta(days=scanner.HISTORY_DAYS))
        return h.loc[mask].copy()
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


def _extract(raw,ticker,batch_len):
    if raw is None or len(raw)==0:return None
    try:
        h=raw[ticker] if batch_len>1 else raw
    except Exception:
        return None
    if h is None or h.empty or 'Close' not in h:return None
    h=h.dropna(how='all').copy()
    return None if h.empty else h


def download_histories(tickers,start,end):
    cache={}; failed=[]
    for i in range(0,len(tickers),BATCH):
        batch=tickers[i:i+BATCH]
        pending=list(batch)
        for attempt in range(RETRIES):
            if not pending:break
            try:
                raw=yf.download(pending,start=start,end=end,group_by='ticker',auto_adjust=True,threads=False,progress=False,timeout=30)
            except Exception:
                raw=None
            next_pending=[]
            for ticker in pending:
                h=_extract(raw,ticker,len(pending))
                if h is None:
                    next_pending.append(ticker)
                else:
                    cache[ticker]=h
            pending=next_pending
            if pending:time.sleep(1.5*(attempt+1))
        for ticker in pending:
            try:
                raw=yf.download(ticker,start=start,end=end,auto_adjust=True,threads=False,progress=False,timeout=30)
                h=_extract(raw,ticker,1)
                if h is not None:cache[ticker]=h
                else:failed.append(ticker)
            except Exception:
                failed.append(ticker)
            time.sleep(.15)
        print('DOWNLOAD',min(i+BATCH,len(tickers)),'/',len(tickers),'ok',len(cache),'failed',len(failed),flush=True)
        time.sleep(.35)
    return cache,sorted(set(failed))


def build_universes():
    universes={}
    all_tickers=[]
    for ds in DATES:
        members=pitindex.get_constituents(ds,index='sp1500')
        tickers=list(dict.fromkeys(str(t).strip().replace('.','-') for t in members['ticker'].tolist()))
        universes[ds]=tickers
        all_tickers.extend(tickers)
    return universes,list(dict.fromkeys(all_tickers))


def run_date(ds,cfg,tickers,cache,download_failed):
    asof=pd.Timestamp(ds); end=asof+pd.Timedelta(days=HORIZON_DAYS)
    tested=[]; failed=[]
    for ticker in tickers:
        h=cache.get(ticker)
        if h is None:
            failed.append(ticker);continue
        try:
            x=calc_asof(ticker,h,cfg,asof)
            hist=restrict_factory(asof)(h)
            if not x or hist.empty:
                failed.append(ticker);continue
            f=forward_stats(h,asof,end,float(hist['Close'].iloc[-1]))
            if not f:
                failed.append(ticker);continue
            row={k:x.get(k) for k in ['rsi','rvol','trend','volatility_pct','support_distance_pct']}
            row['symbol']=ticker
            # Legacy purchase score: rebound/timing model that preceded buy potential.
            row['legacy_score']=float(x.get('timing_v14') or x.get('buy_timing') or 0)
            # New potential formula, unchanged from production/research prototype.
            row['potential_score']=float(potential_score(x))
            row.update(f)
            tested.append(row)
        except Exception:
            failed.append(ticker)
    old_top=sorted(tested,key=lambda x:x['legacy_score'],reverse=True)[:TOP_N]
    new_top=sorted(tested,key=lambda x:x['potential_score'],reverse=True)[:TOP_N]
    old_syms=[x['symbol'] for x in old_top];new_syms=[x['symbol'] for x in new_top]
    overlap=len(set(old_syms)&set(new_syms))
    corr=None
    if len(tested)>=3:
        a=pd.Series([x['legacy_score'] for x in tested],dtype=float)
        b=pd.Series([x['potential_score'] for x in tested],dtype=float)
        c=a.corr(b,method='spearman')
        corr=None if pd.isna(c) else round(float(c),3)
    return {
        'asof':ds,'end':end.strftime('%Y-%m-%d'),'pit_universe':len(tickers),'tested':len(tested),'failed':len(set(failed)),
        'coverage_pct':round(len(tested)/len(tickers)*100,1) if tickers else 0,
        'download_missing_in_universe':len(set(tickers)&set(download_failed)),
        'legacy_top30':summarize(old_top),'potential_top30':summarize(new_top),
        'top30_overlap_n':overlap,'top30_overlap_pct':round(overlap/TOP_N*100,1),'score_spearman':corr,
        'random_top30':random_benchmark(tested,SEED+int(asof.strftime('%Y%m%d'))),'whole_universe':summarize(tested),
        'legacy_symbols':old_syms,'potential_symbols':new_syms,'failed_sample':sorted(set(failed))[:60],
    }


def main():
    cfg=json.loads((ROOT/'config/parameters.json').read_text(encoding='utf-8'))
    universes,all_tickers=build_universes()
    earliest=pd.Timestamp(DATES[0]);latest=pd.Timestamp(DATES[-1])+pd.Timedelta(days=HORIZON_DAYS)
    start=(earliest-pd.Timedelta(days=650)).strftime('%Y-%m-%d')
    dlend=(latest+pd.Timedelta(days=2)).strftime('%Y-%m-%d')
    print('UNION',len(all_tickers),'DOWNLOAD',start,dlend,flush=True)
    cache,download_failed=download_histories(all_tickers,start,dlend)
    results=[]
    for ds in DATES:
        print('RUN',ds,flush=True)
        try:
            r=run_date(ds,cfg,universes[ds],cache,download_failed);results.append(r)
            print(ds,'coverage',r['coverage_pct'],'overlap',r['top30_overlap_pct'],'corr',r['score_spearman'],flush=True)
        except Exception as e:
            results.append({'asof':ds,'error':repr(e)});print('ERROR',ds,repr(e),flush=True)
    good=[r for r in results if 'error' not in r]
    out={'generated':datetime.now(timezone.utc).isoformat(),'protocol':{
        'universe':'S&P 1500 point-in-time reconstructed with pitindex','dates':DATES,'top_n':TOP_N,'horizon_days':HORIZON_DAYS,'random_draws':RANDOM_DRAWS,
        'legacy_comparator':'timing_v14 / buy_timing rebound-timing score (distinct from potential score)',
        'potential_formula':'50% volatility, 20% trend, 15% RVOL, 10% RSI around 40, 5% support proximity',
        'download_strategy':'one union download per historical ticker with batch retries and individual fallback; same cached history reused across all dates',
        'lookahead_control':'scanner history is restricted to <= as-of date before scoring; forward outcomes use only dates after as-of',
        'limitations':['Survivorship-reduced, not perfectly survivorship-free.','Yahoo may still lack histories for some delisted/renamed securities; failures and coverage are reported.','S&P 1500 membership excludes many tiny/speculative issuers and is not a full US-listed-stock universe.']},
        'download':{'union_tickers':len(all_tickers),'downloaded':len(cache),'failed':len(download_failed),'failed_sample':download_failed[:100]},'results':results}
    (ROOT/'data/pit_validation.json').write_text(json.dumps(out,ensure_ascii=False,indent=2),encoding='utf-8')
    lines=['# Point-in-time validation V2','','| Date | Coverage | New final | New peak | >=50 | >=80 | >=100 | >=200 | <10 | Legacy final | Random final | Overlap | Spearman |','|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|']
    for r in good:
        n=r['potential_top30'];o=r['legacy_top30'];rb=r['random_top30']['avg_final_pct']['mean'] if r['random_top30'] else None
        lines.append(f"| {r['asof']} | {r['coverage_pct']}% | {n['avg_final_pct']}% | {n['avg_peak_pct']}% | {n['peak_50_pct']}% | {n['peak_80_pct']}% | {n['peak_100_pct']}% | {n['peak_200_pct']}% | {n['peak_lt10_pct']}% | {o['avg_final_pct']}% | {rb}% | {r['top30_overlap_pct']}% | {r['score_spearman']} |")
    lines+=['','## Protocol corrections','','- Legacy comparator is now `timing_v14` / `buy_timing`, not `score` (which currently aliases the new potential score).','- Historical prices are downloaded once for the union of PIT members, retried, cached, and reused for all as-of dates.','- The production scoring formula is not modified.','','## Limitations','','- Point-in-time S&P 1500 reduces survivorship bias but does not eliminate it.','- Missing Yahoo histories for delisted/renamed names are explicitly counted.','- S&P 1500 is not the full US market and excludes many microcaps/speculative issuers.']
    (ROOT/'data/pit_validation.md').write_text('\n'.join(lines),encoding='utf-8')

if __name__=='__main__':main()
