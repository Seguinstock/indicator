import copy, json, math, os, random, time
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd
import yfinance as yf

import scanner

ROOT = Path(__file__).resolve().parents[1]
SEED = int(os.environ.get('RESEARCH_SEED', '20260910'))
N_PERIODS = int(os.environ.get('RESEARCH_PERIODS', '10'))
WINDOW_DAYS = int(os.environ.get('RESEARCH_WINDOW_DAYS', '50'))
TOP_NS = [30, 100]
START_MIN = pd.Timestamp('2022-01-03')
START_MAX = pd.Timestamp('2026-07-15')

def clip01(x): return float(np.clip(x,0,1))
def nested_set(obj,path,value):
    cur=obj; parts=path.split('.')
    for p in parts[:-1]: cur=cur[p]
    cur[parts[-1]]=value

def default_config(current):
    cfg=copy.deepcopy(current); meta=json.loads((ROOT/'config/parameter_defaults.json').read_text(encoding='utf-8'))
    for path,m in meta.items():
        if not path.startswith('visualisation.'): nested_set(cfg,path,m['default'])
    return cfg

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
    members=pitindex.get_constituents(asof.strftime('%Y-%m-%d'),index='sp500'); seen=set(); rows=[]
    for ticker in members['ticker'].tolist():
        s=str(ticker).strip().upper().replace('.','-')
        if s and s not in seen: seen.add(s); rows.append({'symbol':s,'market':'XNYS','country':'US','enabled':'true'})
    return rows

def restrict_factory(asof):
    def restrict(h):
        h=h.dropna(subset=['Close']).copy()
        if h.empty:return h
        idx=pd.to_datetime(h.index)
        if getattr(idx,'tz',None): idx=idx.tz_localize(None)
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
    closes=f['Close'].astype(float).to_numpy(); lows=f['Low'].astype(float).to_numpy(); highs=f['High'].astype(float).to_numpy()
    return {'return_pct':float((closes[-1]/entry-1)*100),'max_drawdown_pct':float((np.nanmin(lows)/entry-1)*100),'max_upside_pct':float((np.nanmax(highs)/entry-1)*100)}

def q_trend(t):return scanner.TREND_POTENTIAL.get(float(t),0.5)
def q_rsi(r,target,width):return clip01(1-abs(float(r)-target)/width)
def q_rvol(rv,lo=.5,hi=2):return 0 if rv is None or not np.isfinite(rv) else clip01((float(rv)-lo)/(hi-lo))
def q_support(dist,maxd=10):return .5 if dist is None or not np.isfinite(dist) else clip01((maxd-float(dist))/maxd)
def score_weighted(parts):
    total=sum(w for _,w in parts); return 100*sum(q*w for q,w in parts)/total if total else 0

def current_or_default_score(x,cfg):
    s,_=scanner.buy_potential_score(float(x['rsi']),float(x['rvol']) if x['rvol'] is not None else np.nan,float(x['trend']),float(x['volatility_pct']) if x['volatility_pct'] is not None else np.nan,float(x['support_distance_pct']) if x['support_distance_pct'] is not None else np.nan,cfg); return float(s)

def defensive_score(x):
    vol=float(x['volatility_pct']) if x['volatility_pct'] is not None else 100; q_lowvol=1-clip01((vol-15)/45)
    return score_weighted([(q_trend(x['trend']),40),(q_lowvol,30),(q_support(x['support_distance_pct'],8),15),(q_rsi(x['rsi'],40,20),10),(q_rvol(x['rvol'],.6,1.8),5)])

def low_macd_score(x):
    macd=float(x['macd_momentum']) if x['macd_momentum'] is not None else 0; q_low=clip01((-macd)/60) if macd<0 else 0
    return score_weighted([(q_low,50),(q_trend(x['trend']),20),(q_rsi(x['rsi'],33,20),15),(q_rvol(x['rvol']),10),(q_support(x['support_distance_pct']),5)])

def low_rsi_score(x):
    # Deliberately tests the user's intended hypothesis: strongly favor genuinely low RSI.
    # Full RSI component at <=25, fading linearly to zero at RSI 50.
    r=float(x['rsi']); q_low=clip01((50-r)/25)
    return score_weighted([(q_low,55),(q_trend(x['trend']),20),(q_rvol(x['rvol']),10),(q_support(x['support_distance_pct']),10),(clip01((float(x['delta_rsi'])+2)/6),5)])

def confirmed_pullback_score(x):
    macd=float(x['macd_momentum']) if x['macd_momentum'] is not None else 0; dr=float(x['delta_rsi']); vol=float(x['volatility_pct']) if x['volatility_pct'] is not None else 100
    return score_weighted([(q_trend(x['trend']),25),(q_rsi(x['rsi'],35,18),20),(clip01((dr+1)/5),15),(q_rvol(x['rvol'],.6,2),15),(clip01(1-abs(macd+10)/45),15),(clip01(1-abs(vol-40)/35),10)])

def summarize_portfolio(rows,key,n):
    ranked=sorted(rows,key=lambda r:r[key],reverse=True)[:n]; rets=np.array([r['return_pct'] for r in ranked]); dds=np.array([r['max_drawdown_pct'] for r in ranked])
    return {'n':len(ranked),'return_pct':round(float(np.mean(rets)),3),'median_stock_return_pct':round(float(np.median(rets)),3),'win_rate_pct':round(float(np.mean(rets>0)*100),2),'avg_max_drawdown_pct':round(float(np.mean(dds)),3),'symbols':[r['symbol'] for r in ranked]}

def benchmark_return(asof,end):
    h=yf.download('^GSPC',start=(asof-pd.Timedelta(days=10)).strftime('%Y-%m-%d'),end=(end+pd.Timedelta(days=2)).strftime('%Y-%m-%d'),auto_adjust=True,progress=False)
    if h.empty:return None
    c=h['Close']; c=c.iloc[:,0] if isinstance(c,pd.DataFrame) else c; idx=pd.to_datetime(c.index); before=c.loc[idx<=asof]; after=c.loc[(idx>asof)&(idx<=end)]
    if before.empty or after.empty:return None
    return float((float(after.iloc[-1])/float(before.iloc[-1])-1)*100)

def aggregate(period_results,preset,n):
    vals=[]
    for p in period_results:
        r=p['presets'][preset][str(n)]; vals.append((r['return_pct'],p['sp500_return_pct'],r['avg_max_drawdown_pct'],r['win_rate_pct']))
    arr=np.array(vals,dtype=float); excess=arr[:,0]-arr[:,1]
    return {'periods':len(vals),'avg_return_pct':round(float(np.mean(arr[:,0])),3),'median_return_pct':round(float(np.median(arr[:,0])),3),'avg_sp500_return_pct':round(float(np.mean(arr[:,1])),3),'avg_excess_vs_sp500_pct':round(float(np.mean(excess)),3),'median_excess_vs_sp500_pct':round(float(np.median(excess)),3),'beat_sp500_periods':int(np.sum(excess>0)),'positive_periods':int(np.sum(arr[:,0]>0)),'avg_stock_win_rate_pct':round(float(np.mean(arr[:,3])),2),'avg_max_drawdown_pct':round(float(np.mean(arr[:,2])),3),'worst_period_return_pct':round(float(np.min(arr[:,0])),3),'best_period_return_pct':round(float(np.max(arr[:,0])),3)}

def main():
    current_cfg=json.loads((ROOT/'config/parameters.json').read_text(encoding='utf-8')); default_cfg=default_config(current_cfg); periods=pick_periods(); output=[]
    for pi,asof in enumerate(periods,1):
        end=asof+pd.Timedelta(days=WINDOW_DAYS); rows=pit_rows(asof); download_start=(asof-pd.Timedelta(days=650)).strftime('%Y-%m-%d'); download_end=(end+pd.Timedelta(days=2)).strftime('%Y-%m-%d'); tested=[]; failed=[]
        for i in range(0,len(rows),75):
            batch=rows[i:i+75]; tickers=[scanner.yahoo_symbol(r['symbol'],r['market']) for r in batch]
            try:raw=yf.download(tickers,start=download_start,end=download_end,interval='1d',group_by='ticker',auto_adjust=True,threads=True,progress=False)
            except Exception:failed.extend(r['symbol'] for r in batch);continue
            for row,t in zip(batch,tickers):
                try:
                    h=raw[t] if len(tickers)>1 else raw; x=calc_features(row,h,current_cfg,asof)
                    if not x:failed.append(row['symbol']);continue
                    hist=restrict_factory(asof)(h)
                    if hist.empty:failed.append(row['symbol']);continue
                    fwd=forward_stats(h,asof,end,float(hist['Close'].astype(float).iloc[-1]))
                    if not fwd:failed.append(row['symbol']);continue
                    rec={k:x.get(k) for k in ['symbol','rsi','delta_rsi','rvol','support_distance_pct','macd_momentum','trend','volatility_pct']}; rec.update(fwd)
                    rec.update(score_current=current_or_default_score(x,current_cfg),score_default=current_or_default_score(x,default_cfg),score_defensive=defensive_score(x),score_low_macd=low_macd_score(x),score_low_rsi=low_rsi_score(x),score_confirmed_pullback=confirmed_pullback_score(x)); tested.append(rec)
                except Exception:failed.append(row['symbol'])
            time.sleep(.25)
        b=benchmark_return(asof,end)
        if b is None:raise RuntimeError(f'Benchmark indisponible {asof.date()}')
        pairs=[('current','score_current'),('default','score_default'),('defensive','score_defensive'),('low_macd','score_low_macd'),('low_rsi','score_low_rsi'),('confirmed_pullback','score_confirmed_pullback')]
        presets={name:{str(n):summarize_portfolio(tested,key,n) for n in TOP_NS} for name,key in pairs}
        output.append({'period':pi,'asof':asof.strftime('%Y-%m-%d'),'end':end.strftime('%Y-%m-%d'),'universe':'sp500_pit','universe_count':len(rows),'tested':len(tested),'failed':len(set(failed)),'sp500_return_pct':round(b,3),'presets':presets}); print(f'{pi}/{len(periods)} {asof.date()}->{end.date()} tested={len(tested)} S&P={b:.2f}%')
    names=['current','default','defensive','low_macd','low_rsi','confirmed_pullback']; aggregate_out={name:{str(n):aggregate(output,name,n) for n in TOP_NS} for name in names}; benchmark_avg=round(float(np.mean([p['sp500_return_pct'] for p in output])),3)
    result={'generated':datetime.now(timezone.utc).isoformat(),'seed':SEED,'window_days':WINDOW_DAYS,'periods':N_PERIODS,'methodology':{'universe':'Historical S&P 500 point-in-time membership via pitindex on each as-of date','selection':'Same deterministic random 50-calendar-day windows for every preset; starts are business days and at least 65 days apart','portfolio':'Equal-weight Top 30 and Top 100 ranked stocks; return measured from last close on/before as-of to last close on/before end','benchmark':'S&P 500 price index (^GSPC) over the identical window','survivorship_bias':'Historical point-in-time membership used; unavailable historical tickers are reported as failed rather than replaced with current constituents'},'preset_definitions':{'current':current_cfg['buy_model'],'default':default_cfg['buy_model'],'defensive':'40% trend, 30% low volatility, 15% support, 10% RSI near 40, 5% RVOL','low_macd':'50% low negative MACD, 20% trend, 15% RSI near 33, 10% RVOL, 5% support','low_rsi':'55% genuinely low RSI (full <=25, zero at 50), 20% trend, 10% RVOL, 10% support, 5% RSI reversal','confirmed_pullback':'25% trend, 20% RSI near 35, 15% RSI rebound, 15% RVOL, 15% MACD near -10, 10% moderate volatility'},'benchmark_avg_return_pct':benchmark_avg,'aggregate':aggregate_out,'period_results':output}
    (ROOT/'data/research_backtest_50.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8'); print(json.dumps({'benchmark_avg_return_pct':benchmark_avg,'aggregate':aggregate_out},ensure_ascii=False,indent=2))

if __name__=='__main__':main()
