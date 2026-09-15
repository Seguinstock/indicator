import csv, json, time, os, math
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd
import yfinance as yf

import scanner
import relative_strength_runtime as rs_runtime

ROOT = Path(__file__).resolve().parents[1]
ASOF = pd.Timestamp(os.environ.get('BACKTEST_ASOF', '2026-05-01'))
END = pd.Timestamp(os.environ.get('BACKTEST_END', (ASOF + pd.Timedelta(days=28)).strftime('%Y-%m-%d')))
UNIVERSE_MODE = os.environ.get('BACKTEST_UNIVERSE', 'current').strip().lower()


def restrict_asof(h):
    h = h.dropna(subset=['Close']).copy()
    if h.empty: return h
    idx = pd.to_datetime(h.index).tz_localize(None) if getattr(pd.to_datetime(h.index), 'tz', None) else pd.to_datetime(h.index)
    return h.loc[(idx <= ASOF) & (idx >= ASOF - pd.Timedelta(days=scanner.HISTORY_DAYS))].copy()


def calc_asof(row,h,cfg):
    old=scanner.restrict_v14_history; scanner.restrict_v14_history=restrict_asof
    try: return scanner.calc(row,h,cfg)
    finally: scanner.restrict_v14_history=old


def close_asof(h):
    return rs_runtime._close_series(restrict_asof(h))


def market_return_20_asof():
    start=(ASOF-pd.Timedelta(days=120)).strftime('%Y-%m-%d')
    end=(ASOF+pd.Timedelta(days=1)).strftime('%Y-%m-%d')
    for symbol in ('^SP1500','^GSPC'):
        try:
            h=yf.download(symbol,start=start,end=end,interval='1d',auto_adjust=True,progress=False)
            c=rs_runtime._close_series(h)
            if len(c)>20:return rs_runtime._period_return(c,20),symbol
        except Exception:continue
    return 0.0,'unavailable'


def apply_tableau_score(x,h,cfg,market20):
    c=close_asof(h)
    ret20=rs_runtime._period_return(c,20)
    ret60=rs_runtime._period_return(c,60)
    rel20=ret20-market20
    # Exact same scoring function and same rounded scanner inputs as Tableau.
    score,components=rs_runtime.relative_strength_score(x['rsi'],x['rvol'],x['trend'],ret20,ret60,rel20,cfg)
    y=dict(x)
    y['return_20_pct']=round(ret20,2)
    y['return_60_pct']=round(ret60,2)
    y['relative_strength_20_pct']=round(rel20,2)
    y['potential_components']=components
    y['potential_score']=round(score,1)
    y['score']=round(score,1)
    return y


def finite_or_none(v):
    try:
        v=float(v); return v if math.isfinite(v) else None
    except Exception:return None


def forward_stats(h,entry):
    idx=pd.to_datetime(h.index).tz_localize(None) if getattr(pd.to_datetime(h.index),'tz',None) else pd.to_datetime(h.index)
    f=h.loc[(idx>ASOF)&(idx<=END)].copy()
    if f.empty:return None
    closes=f['Close'].astype(float).to_numpy(); lows=f['Low'].astype(float).to_numpy(); highs=f['High'].astype(float).to_numpy()
    end_price=float(closes[-1]); low=finite_or_none(np.nanmin(lows)) if np.isfinite(lows).any() else None; high=finite_or_none(np.nanmax(highs)) if np.isfinite(highs).any() else None
    return {'end_price':round(end_price,4),'return_pct':round((end_price/entry-1)*100,2),'max_drawdown_pct':round((low/entry-1)*100,2) if low is not None else None,'max_upside_pct':round((high/entry-1)*100,2) if high is not None else None}


def bucket(v):
    if v>=80:return '80-100'
    if v>=70:return '70-79.9'
    if v>=60:return '60-69.9'
    if v>=50:return '50-59.9'
    if v>=40:return '40-49.9'
    return '<40'


def summarize(rows):
    out={}
    for name in ['80-100','70-79.9','60-69.9','50-59.9','40-49.9','<40']:
        a=[r for r in rows if r['bucket']==name]
        if not a:continue
        rets=np.array([r['return_pct'] for r in a],dtype=float); dds=np.array([np.nan if r['max_drawdown_pct'] is None else r['max_drawdown_pct'] for r in a],dtype=float)
        out[name]={'n':len(a),'avg_return_pct':round(float(np.nanmean(rets)),2),'median_return_pct':round(float(np.nanmedian(rets)),2),'win_rate_pct':round(float(np.mean(rets>0)*100),1),'avg_max_drawdown_pct':round(float(np.nanmean(dds)),2) if np.isfinite(dds).any() else None}
    return out


def filter_effect(rows,key):
    yes=[r for r in rows if r['filters'].get(key) is True]; no=[r for r in rows if r['filters'].get(key) is False]
    def s(a):
        if not a:return None
        x=np.array([r['return_pct'] for r in a],dtype=float); return {'n':len(a),'avg_return_pct':round(float(np.nanmean(x)),2),'median_return_pct':round(float(np.nanmedian(x)),2),'win_rate_pct':round(float(np.mean(x>0)*100),1)}
    return {'pass':s(yes),'fail':s(no)}


def clean_json(v):
    if isinstance(v,dict):return {k:clean_json(x) for k,x in v.items()}
    if isinstance(v,list):return [clean_json(x) for x in v]
    if isinstance(v,np.bool_):return bool(v)
    if isinstance(v,np.integer):return int(v)
    if isinstance(v,(np.floating,float)):
        x=float(v); return x if math.isfinite(x) else None
    return v


def current_rows():
    with open(ROOT/'config/symbols.csv',encoding='utf-8-sig') as f:return [r for r in csv.DictReader(f) if r.get('enabled','true').lower()=='true']


def pit_rows(index_name,earliest):
    if ASOF<pd.Timestamp(earliest):raise ValueError(f'Historical {index_name.upper()} point-in-time mode is available from {earliest} onward')
    import pitindex
    members=pitindex.get_constituents(ASOF.strftime('%Y-%m-%d'),index=index_name); tickers=[]; seen=set()
    for ticker in members['ticker'].tolist():
        symbol=str(ticker).strip().upper().replace('.','-')
        if symbol and symbol not in seen:seen.add(symbol);tickers.append(symbol)
    if not tickers:raise ValueError(f'No historical {index_name.upper()} constituents found for requested date')
    return [{'symbol':s,'market':'XNYS','country':'US','enabled':'true'} for s in tickers]


def universe_rows():
    if UNIVERSE_MODE=='sp500_pit':return pit_rows('sp500','2005-01-01'),'S&P 500 historique'
    if UNIVERSE_MODE=='sp1500_pit':return pit_rows('sp1500','2021-03-26'),'S&P 1500 historique'
    if UNIVERSE_MODE!='current':raise ValueError(f'Unsupported backtest universe: {UNIVERSE_MODE}')
    return current_rows(),'Ma liste actuelle'


def main():
    cfg=json.loads((ROOT/'config/parameters.json').read_text(encoding='utf-8'))
    rows,universe_label=universe_rows(); tested=[]; failed=[]
    market20,benchmark_symbol=market_return_20_asof()
    download_start=(ASOF-pd.Timedelta(days=650)).strftime('%Y-%m-%d'); download_end=(END+pd.Timedelta(days=1)).strftime('%Y-%m-%d')
    for i in range(0,len(rows),75):
        batch=rows[i:i+75]; tickers=[scanner.yahoo_symbol(r['symbol'],r['market']) for r in batch]
        try:raw=yf.download(tickers,start=download_start,end=download_end,interval='1d',group_by='ticker',auto_adjust=True,threads=True,progress=False)
        except Exception:failed.extend(r['symbol'] for r in batch);continue
        for r,t in zip(batch,tickers):
            try:
                h=raw[t] if len(tickers)>1 else raw
                base=calc_asof(r,h,cfg)
                if not base:failed.append(r['symbol']);continue
                x=apply_tableau_score(base,h,cfg,market20)
                hist=restrict_asof(h)
                if hist.empty:failed.append(r['symbol']);continue
                entry=float(hist['Close'].astype(float).iloc[-1]); fwd=forward_stats(h,entry)
                if not fwd:failed.append(r['symbol']);continue
                keys=['symbol','market','country','price','rsi','delta_rsi','rvol','support_distance_pct','support_score','macd_momentum','trend','volatility_pct','return_20_pct','return_60_pct','relative_strength_20_pct','potential_components','score']
                y={k:x[k] for k in keys}; y['filters']={k:bool(v) for k,v in x['filters'].items()}; y['passed']=bool(x['passed']); y.update(fwd); y['bucket']=bucket(float(x['score'])); tested.append(clean_json(y))
            except Exception:failed.append(r['symbol'])
        time.sleep(.5)
    tested.sort(key=lambda r:r['score'],reverse=True); filters=['rsi','reversal','support','rvol','macd','trend']
    out={'generated':datetime.now(timezone.utc).isoformat(),'asof':ASOF.strftime('%Y-%m-%d'),'end':END.strftime('%Y-%m-%d'),'universe_mode':UNIVERSE_MODE,'universe_label':universe_label,'universe':len(rows),'tested':len(tested),'failed':len(set(failed)),'buy_model':'relative_strength_v1','benchmark_20d_symbol':benchmark_symbol,'benchmark_20d_return_pct':round(market20,3),'parameter_snapshot':cfg,'score_buckets':summarize(tested),'filter_effects':{k:filter_effect(tested,k) for k in filters},'strict_pass':summarize([r for r in tested if r['passed']]),'top_by_score':tested[:50],'all_rows':tested}
    (ROOT/'data/backtest.json').write_text(json.dumps(clean_json(out),ensure_ascii=False,indent=2,allow_nan=False),encoding='utf-8')
    print(f"Backtest Tableau RS {ASOF.date()} -> {END.date()} [{universe_label}] : {len(tested)}/{len(rows)} benchmark20={market20:.2f}% ({benchmark_symbol})")

if __name__=='__main__':main()
