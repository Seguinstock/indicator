import json, os, random, time
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd
import yfinance as yf

import scanner

ROOT=Path(__file__).resolve().parents[1]
SEED=int(os.environ.get('RESEARCH_SEED','20260910'))
N_PERIODS=int(os.environ.get('RESEARCH_PERIODS','16'))
WINDOW_DAYS=int(os.environ.get('RESEARCH_WINDOW_DAYS','50'))
TOP_NS=[30,100]
START_MIN=pd.Timestamp('2021-04-01')
START_MAX=pd.Timestamp('2026-07-15')


def clip01(x): return float(np.clip(x,0,1))
def q_trend(t): return scanner.TREND_POTENTIAL.get(float(t),0.5)
def q_rsi(r,target,width): return clip01(1-abs(float(r)-target)/width)
def q_rvol(rv,lo=.6,hi=2.0): return 0 if rv is None or not np.isfinite(rv) else clip01((float(rv)-lo)/(hi-lo))
def q_support(dist,maxd=8): return .5 if dist is None or not np.isfinite(dist) else clip01((maxd-float(dist))/maxd)
def q_lowvol(v,lo=15,hi=60):
    x=100 if v is None or not np.isfinite(v) else float(v)
    return 1-clip01((x-lo)/(hi-lo))
def q_macd_low(m):
    x=0 if m is None or not np.isfinite(m) else float(m)
    return clip01((-x)/60) if x<0 else 0
def q_macd_near(m,target=-10,width=45):
    x=0 if m is None or not np.isfinite(m) else float(m)
    return clip01(1-abs(x-target)/width)
def q_rebound(dr,lo=-1,hi=4): return clip01((float(dr)-lo)/(hi-lo))
def score(parts):
    total=sum(w for _,w in parts)
    return 100*sum(q*w for q,w in parts)/total if total else 0


def defensive(x):
    return score([(q_trend(x['trend']),40),(q_lowvol(x['volatility_pct']),30),(q_support(x['support_distance_pct'],8),15),(q_rsi(x['rsi'],40,20),10),(q_rvol(x['rvol'],.6,1.8),5)])
def low_macd(x):
    return score([(q_macd_low(x['macd_momentum']),50),(q_trend(x['trend']),20),(q_rsi(x['rsi'],33,20),15),(q_rvol(x['rvol']),10),(q_support(x['support_distance_pct'],10),5)])
def confirmed_pullback(x):
    return score([(q_trend(x['trend']),25),(q_rsi(x['rsi'],35,18),20),(q_rebound(x['delta_rsi']),15),(q_rvol(x['rvol'],.6,2),15),(q_macd_near(x['macd_momentum'],-10,45),15),(1-abs(q_lowvol(x['volatility_pct'],15,60)-.55),10)])

def defensive_rebound(x):
    return score([(q_trend(x['trend']),35),(q_lowvol(x['volatility_pct'],15,55),25),(q_rsi(x['rsi'],38,18),15),(q_rebound(x['delta_rsi'],-1,4),10),(q_support(x['support_distance_pct'],7),10),(q_rvol(x['rvol'],.6,1.8),5)])
def early_reversal(x):
    return score([(q_macd_near(x['macd_momentum'],-20,35),25),(q_rebound(x['delta_rsi'],-2,3),25),(q_trend(x['trend']),20),(q_rsi(x['rsi'],34,16),15),(q_lowvol(x['volatility_pct'],18,65),10),(q_rvol(x['rvol'],.5,1.8),5)])
def balanced_quality_dip(x):
    return score([(q_trend(x['trend']),30),(q_lowvol(x['volatility_pct'],15,55),20),(q_rsi(x['rsi'],37,20),15),(q_rebound(x['delta_rsi'],-1,5),15),(q_support(x['support_distance_pct'],8),10),(q_rvol(x['rvol'],.6,1.8),10)])

STRATEGIES={
 'defensive':defensive,
 'low_macd':low_macd,
 'confirmed_pullback':confirmed_pullback,
 'defensive_rebound':defensive_rebound,
 'early_reversal':early_reversal,
 'balanced_quality_dip':balanced_quality_dip,
}


def pick_periods():
    candidates=list(pd.bdate_range(START_MIN,START_MAX)); rng=random.Random(SEED); rng.shuffle(candidates); chosen=[]
    for d in candidates:
        if all(abs((d-x).days)>=65 for x in chosen):
            chosen.append(d)
            if len(chosen)==N_PERIODS: break
    if len(chosen)<N_PERIODS: raise RuntimeError('Impossible de générer assez de fenêtres distinctes')
    return sorted(chosen)


def pit_rows(asof):
    import pitindex
    members=pitindex.get_constituents(asof.strftime('%Y-%m-%d'),index='sp1500'); seen=set(); out=[]
    for ticker in members['ticker'].tolist():
        s=str(ticker).strip().upper().replace('.','-')
        if s and s not in seen: seen.add(s); out.append({'symbol':s,'market':'XNYS','country':'US','enabled':'true'})
    return out


def restrict_factory(asof):
    def restrict(h):
        h=h.dropna(subset=['Close']).copy()
        if h.empty:return h
        idx=pd.to_datetime(h.index)
        if getattr(idx,'tz',None):idx=idx.tz_localize(None)
        return h.loc[(idx<=asof)&(idx>=asof-pd.Timedelta(days=scanner.HISTORY_DAYS))].copy()
    return restrict


def calc_features(row,h,cfg,asof):
    old=scanner.restrict_v14_history; scanner.restrict_v14_history=restrict_factory(asof)
    try:return scanner.calc(row,h,cfg)
    finally:scanner.restrict_v14_history=old


def forward_stats(h,asof,end,entry):
    idx=pd.to_datetime(h.index)
    if getattr(idx,'tz',None):idx=idx.tz_localize(None)
    f=h.loc[(idx>asof)&(idx<=end)].copy()
    if f.empty:return None
    closes=f['Close'].astype(float).to_numpy(); lows=f['Low'].astype(float).to_numpy()
    return {'return_pct':float((closes[-1]/entry-1)*100),'max_drawdown_pct':float((np.nanmin(lows)/entry-1)*100)}


def benchmark(symbol,asof,end):
    h=yf.download(symbol,start=(asof-pd.Timedelta(days=10)).strftime('%Y-%m-%d'),end=(end+pd.Timedelta(days=2)).strftime('%Y-%m-%d'),auto_adjust=True,progress=False)
    if h.empty:return None
    c=h['Close']; c=c.iloc[:,0] if isinstance(c,pd.DataFrame) else c; idx=pd.to_datetime(c.index); before=c.loc[idx<=asof]; after=c.loc[(idx>asof)&(idx<=end)]
    if before.empty or after.empty:return None
    return float((float(after.iloc[-1])/float(before.iloc[-1])-1)*100)


def portfolio(rows,key,n):
    ranked=sorted(rows,key=lambda r:r[key],reverse=True)[:n]
    rets=np.array([r['return_pct'] for r in ranked]); dds=np.array([r['max_drawdown_pct'] for r in ranked])
    return {'n':len(ranked),'return_pct':round(float(np.mean(rets)),3),'median_stock_return_pct':round(float(np.median(rets)),3),'win_rate_pct':round(float(np.mean(rets>0)*100),2),'avg_max_drawdown_pct':round(float(np.mean(dds)),3),'symbols':[r['symbol'] for r in ranked]}


def aggregate(periods,name,n):
    vals=[]
    for p in periods:
        r=p['strategies'][name][str(n)]; vals.append((r['return_pct'],p['benchmark_return_pct'],r['avg_max_drawdown_pct'],r['win_rate_pct']))
    a=np.array(vals,float); ex=a[:,0]-a[:,1]
    return {'periods':len(vals),'avg_return_pct':round(float(np.mean(a[:,0])),3),'median_return_pct':round(float(np.median(a[:,0])),3),'avg_benchmark_return_pct':round(float(np.mean(a[:,1])),3),'avg_excess_pct':round(float(np.mean(ex)),3),'median_excess_pct':round(float(np.median(ex)),3),'beat_benchmark_periods':int(np.sum(ex>0)),'positive_periods':int(np.sum(a[:,0]>0)),'avg_stock_win_rate_pct':round(float(np.mean(a[:,3])),2),'avg_max_drawdown_pct':round(float(np.mean(a[:,2])),3),'worst_period_return_pct':round(float(np.min(a[:,0])),3),'best_period_return_pct':round(float(np.max(a[:,0])),3)}


def main():
    cfg=json.loads((ROOT/'config/parameters.json').read_text(encoding='utf-8')); periods=[]
    for pi,asof in enumerate(pick_periods(),1):
        end=asof+pd.Timedelta(days=WINDOW_DAYS); rows=pit_rows(asof); tested=[]; failed=[]
        ds=(asof-pd.Timedelta(days=650)).strftime('%Y-%m-%d'); de=(end+pd.Timedelta(days=2)).strftime('%Y-%m-%d')
        for i in range(0,len(rows),75):
            batch=rows[i:i+75]; tickers=[scanner.yahoo_symbol(r['symbol'],r['market']) for r in batch]
            try: raw=yf.download(tickers,start=ds,end=de,interval='1d',group_by='ticker',auto_adjust=True,threads=True,progress=False)
            except Exception: failed.extend(r['symbol'] for r in batch); continue
            for row,t in zip(batch,tickers):
                try:
                    h=raw[t] if len(tickers)>1 else raw; x=calc_features(row,h,cfg,asof)
                    if not x: failed.append(row['symbol']); continue
                    hist=restrict_factory(asof)(h)
                    if hist.empty: failed.append(row['symbol']); continue
                    f=forward_stats(h,asof,end,float(hist['Close'].astype(float).iloc[-1]))
                    if not f: failed.append(row['symbol']); continue
                    rec={k:x.get(k) for k in ['symbol','rsi','delta_rsi','rvol','support_distance_pct','macd_momentum','trend','volatility_pct']}; rec.update(f)
                    for name,fn in STRATEGIES.items(): rec['score_'+name]=fn(x)
                    tested.append(rec)
                except Exception: failed.append(row['symbol'])
            time.sleep(.2)
        b1500=benchmark('^SP1500',asof,end); b500=benchmark('^GSPC',asof,end)
        chosen=b1500 if b1500 is not None else b500
        if chosen is None: raise RuntimeError(f'Benchmark unavailable {asof.date()}')
        results={name:{str(n):portfolio(tested,'score_'+name,n) for n in TOP_NS} for name in STRATEGIES}
        periods.append({'period':pi,'asof':asof.strftime('%Y-%m-%d'),'end':end.strftime('%Y-%m-%d'),'universe':'sp1500_pit','universe_count':len(rows),'tested':len(tested),'failed':len(set(failed)),'sp1500_return_pct':round(b1500,3) if b1500 is not None else None,'sp500_return_pct':round(b500,3) if b500 is not None else None,'benchmark_return_pct':round(chosen,3),'benchmark_used':'^SP1500' if b1500 is not None else '^GSPC','strategies':results})
        print(f'{pi}/{N_PERIODS} {asof.date()} tested={len(tested)}/{len(rows)} benchmark={chosen:.2f}%')
    agg={name:{str(n):aggregate(periods,name,n) for n in TOP_NS} for name in STRATEGIES}
    out={'generated':datetime.now(timezone.utc).isoformat(),'seed':SEED,'window_days':WINDOW_DAYS,'periods':N_PERIODS,'universe':'S&P 1500 historical point-in-time','strategy_definitions':{'defensive':'40 trend, 30 low volatility, 15 support, 10 RSI near 40, 5 RVOL','low_macd':'50 low negative MACD, 20 trend, 15 RSI near 33, 10 RVOL, 5 support','confirmed_pullback':'25 trend, 20 RSI near 35, 15 RSI rebound, 15 RVOL, 15 MACD near -10, 10 moderate volatility','defensive_rebound':'35 trend, 25 low volatility, 15 RSI near 38, 10 RSI rebound, 10 support, 5 RVOL','early_reversal':'25 MACD near -20, 25 RSI rebound, 20 trend, 15 RSI near 34, 10 low/moderate volatility, 5 RVOL','balanced_quality_dip':'30 trend, 20 low volatility, 15 RSI near 37, 15 RSI rebound, 10 support, 10 RVOL'},'aggregate':agg,'period_results':periods}
    (ROOT/'data/research_sp1500.json').write_text(json.dumps(out,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(agg,ensure_ascii=False,indent=2))

if __name__=='__main__': main()
