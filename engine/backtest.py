import csv, json, time
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd
import yfinance as yf

import scanner

ROOT = Path(__file__).resolve().parents[1]
ASOF = pd.Timestamp('2026-05-01')
END = pd.Timestamp('2026-05-29')


def restrict_asof(h):
    h = h.dropna(subset=['Close']).copy()
    if h.empty:
        return h
    idx = pd.to_datetime(h.index).tz_localize(None) if getattr(pd.to_datetime(h.index), 'tz', None) else pd.to_datetime(h.index)
    mask = (idx <= ASOF) & (idx >= ASOF - pd.Timedelta(days=scanner.HISTORY_DAYS))
    return h.loc[mask].copy()


def calc_asof(row, h, cfg):
    old = scanner.restrict_v14_history
    scanner.restrict_v14_history = restrict_asof
    try:
        return scanner.calc(row, h, cfg)
    finally:
        scanner.restrict_v14_history = old


def forward_stats(h, entry):
    idx = pd.to_datetime(h.index).tz_localize(None) if getattr(pd.to_datetime(h.index), 'tz', None) else pd.to_datetime(h.index)
    f = h.loc[(idx > ASOF) & (idx <= END)].copy()
    if f.empty:
        return None
    closes = f['Close'].astype(float).to_numpy()
    lows = f['Low'].astype(float).to_numpy()
    highs = f['High'].astype(float).to_numpy()
    end_price = float(closes[-1])
    return {
        'end_price': round(end_price, 4),
        'return_pct': round((end_price / entry - 1) * 100, 2),
        'max_drawdown_pct': round((float(np.min(lows)) / entry - 1) * 100, 2),
        'max_upside_pct': round((float(np.max(highs)) / entry - 1) * 100, 2),
    }


def bucket(v):
    if v >= 80: return '80-100'
    if v >= 70: return '70-79.9'
    if v >= 60: return '60-69.9'
    if v >= 50: return '50-59.9'
    if v >= 40: return '40-49.9'
    return '<40'


def summarize(rows):
    out = {}
    for name in ['80-100','70-79.9','60-69.9','50-59.9','40-49.9','<40']:
        a=[r for r in rows if r['bucket']==name]
        if not a: continue
        rets=np.array([r['return_pct'] for r in a],dtype=float)
        dds=np.array([r['max_drawdown_pct'] for r in a],dtype=float)
        out[name]={
            'n':len(a),
            'avg_return_pct':round(float(np.mean(rets)),2),
            'median_return_pct':round(float(np.median(rets)),2),
            'win_rate_pct':round(float(np.mean(rets>0)*100),1),
            'avg_max_drawdown_pct':round(float(np.mean(dds)),2),
        }
    return out


def filter_effect(rows, key):
    yes=[r for r in rows if r['filters'].get(key) is True]
    no=[r for r in rows if r['filters'].get(key) is False]
    def s(a):
        if not a: return None
        x=np.array([r['return_pct'] for r in a],dtype=float)
        return {'n':len(a),'avg_return_pct':round(float(np.mean(x)),2),'median_return_pct':round(float(np.median(x)),2),'win_rate_pct':round(float(np.mean(x>0)*100),1)}
    return {'pass':s(yes),'fail':s(no)}


def main():
    cfg=json.loads((ROOT/'config/parameters.json').read_text(encoding='utf-8'))
    with open(ROOT/'config/symbols.csv',encoding='utf-8-sig') as f:
        rows=[r for r in csv.DictReader(f) if r.get('enabled','true').lower()=='true']
    tested=[]; failed=[]
    for i in range(0,len(rows),75):
        batch=rows[i:i+75]
        tickers=[scanner.yahoo_symbol(r['symbol'],r['market']) for r in batch]
        try:
            raw=yf.download(tickers,start='2024-12-01',end='2026-05-30',interval='1d',group_by='ticker',auto_adjust=True,threads=True,progress=False)
        except Exception:
            failed.extend(r['symbol'] for r in batch); continue
        for r,t in zip(batch,tickers):
            try:
                h=raw[t] if len(tickers)>1 else raw
                x=calc_asof(r,h,cfg)
                if not x: failed.append(r['symbol']); continue
                hist=restrict_asof(h)
                if hist.empty: failed.append(r['symbol']); continue
                entry=float(hist['Close'].astype(float).iloc[-1])
                fwd=forward_stats(h,entry)
                if not fwd: failed.append(r['symbol']); continue
                y={k:x[k] for k in ['symbol','market','country','price','rsi','delta_rsi','rvol','support_distance_pct','support_score','macd_momentum','trend','volatility_pct','score']}
                y['filters']={k:bool(v) for k,v in x['filters'].items()}
                y['passed']=bool(x['passed'])
                y.update(fwd); y['bucket']=bucket(float(x['score']))
                tested.append(y)
            except Exception:
                failed.append(r['symbol'])
        time.sleep(1)
    tested.sort(key=lambda r:r['score'],reverse=True)
    filters=['rsi','reversal','support','rvol','macd','trend']
    out={
        'generated':datetime.now(timezone.utc).isoformat(),
        'asof':'2026-05-01','end':'2026-05-29',
        'universe':len(rows),'tested':len(tested),'failed':len(set(failed)),
        'score_buckets':summarize(tested),
        'filter_effects':{k:filter_effect(tested,k) for k in filters},
        'strict_pass':summarize([r for r in tested if r['passed']]),
        'top_by_score':tested[:50],
        'all_rows':tested,
    }
    (ROOT/'data/backtest.json').write_text(json.dumps(out,ensure_ascii=False,indent=2),encoding='utf-8')
    print(f"Backtest {len(tested)}/{len(rows)}")

if __name__=='__main__':
    main()
