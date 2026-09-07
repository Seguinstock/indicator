import csv, json, math, time
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd
import yfinance as yf

ROOT = Path(__file__).resolve().parents[1]
HISTORY_DAYS = 500
VOL_WINDOW = 252
TRADING_DAYS = 252
MACD_FAST, MACD_SLOW, MACD_SIGNAL, MACD_LOOKBACK = 12, 26, 9, 20
MACD_MOM_WEIGHTS = (0.60, 0.30, 0.10)
MACD_ACC_WEIGHTS = (0.70, 0.30)
MACD_TANH_SENSITIVITY = 1.50
MACD_COMPONENT_WEIGHTS = (0.55, 0.30, 0.15)
MACD_MAX_INDEX = 100.0
MACD_TIMING_IMPACT = 10.0
SUPPORT_MIN_HISTORY, SUPPORT_MAX_AGE, SUPPORT_HALF_WINDOW = 250, 200, 3
SUPPORT_GROUP_TOL = 0.015
SUPPORT_MAX_REACTIONS, SUPPORT_POINTS_PER_REACTION = 4, 8
SUPPORT_RECENCY_MAX, SUPPORT_RECENCY_DECAY, SUPPORT_PROXIMITY_MAX = 15, 0.075, 10
SUPPORT_AGE_VERY_RECENT, SUPPORT_AGE_RECENT = 20, 50
SUPPORT_BASE_VERY_RECENT, SUPPORT_BASE_RECENT, SUPPORT_BASE_OLD = 50, 30, 20
SUPPORT_STRONG, SUPPORT_MEDIUM = 70, 45
TREND_FAST, TREND_SLOW, TREND_SLOPE_BACK = 50, 200, 20
TREND_BUY_FACTORS = {1: 1.05, -0.5: 0.90, -1: 0.85, -2: 0.70}
TREND_SELL_FACTORS = {-1: 1.05, 0.5: 0.90, 1: 0.85, 2: 0.70}


def yahoo_symbol(symbol, market):
    s = symbol.replace('.', '-')
    if market == 'XTSE': return s + '.TO'
    if market == 'XTSX': return s + '.V'
    if market == 'XCNQ': return s + '.CN'
    return s


def restrict_v14_history(h):
    h = h.dropna(subset=['Close']).copy()
    if h.empty: return h
    idx = pd.to_datetime(h.index)
    today = pd.Timestamp.now(tz=idx.tz).normalize() if getattr(idx, 'tz', None) else pd.Timestamp.now().normalize()
    return h.loc[idx >= today - pd.Timedelta(days=HISTORY_DAYS)].copy()


def wilder_rsi(close, period):
    x = np.asarray(close, dtype=float)
    if len(x) < period + 3: return np.nan, np.nan
    d = np.diff(x); up = np.where(d > 0, d, 0.0); dn = np.where(d < 0, -d, 0.0)
    ag = float(np.mean(up[:period])); al = float(np.mean(dn[:period])); values = []
    values.append(100.0 if al == 0 else 100.0 - 100.0 / (1.0 + ag / al))
    for u, l in zip(up[period:], dn[period:]):
        ag = (ag * (period - 1) + float(u)) / period
        al = (al * (period - 1) + float(l)) / period
        values.append(100.0 if al == 0 else 100.0 - 100.0 / (1.0 + ag / al))
    return float(values[-1]), float(values[-2])


def seeded_ema(values, period):
    x = np.asarray(values, dtype=float)
    if len(x) < period: return np.array([], dtype=float)
    alpha = 2.0 / (period + 1.0); e = float(np.mean(x[:period])); out = [e]
    for v in x[period:]:
        e = e + alpha * (float(v) - e); out.append(e)
    return np.asarray(out, dtype=float)


def sample_std(x):
    x = np.asarray(x, dtype=float)
    return 0.0 if len(x) < 2 else float(np.std(x, ddof=1))


def macd_v14(close):
    c = np.asarray(close, dtype=float); ef = seeded_ema(c, MACD_FAST); es = seeded_ema(c, MACD_SLOW)
    if len(es) == 0: return np.nan
    mline = ef[-len(es):] - es; signal = seeded_ema(mline, MACD_SIGNAL)
    if len(signal) < 4: return np.nan
    hist = mline[-len(signal):] - signal; hd = np.diff(hist); ha = np.diff(hd)
    if len(hd) < 3: return np.nan
    md0, md1, md2 = float(hd[-1]), float(hd[-2]), float(hd[-3])
    mmom = .60*md0 + .30*md1 + .10*md2
    macc = .70*(md0-md1) + .30*(md1-md2); mhc = float(hist[-1])
    mmomstd = sample_std(hd[-min(MACD_LOOKBACK,len(hd)):]); maccstd = sample_std(ha[-min(MACD_LOOKBACK,len(ha)):]); mhiststd = sample_std(hist[-min(MACD_LOOKBACK,len(hist)):])
    momz = 0 if mmomstd == 0 else mmom/mmomstd; accz = 0 if maccstd == 0 else macc/maccstd; posz = 0 if mhiststd == 0 else mhc/mhiststd
    idx = .55*(100*math.tanh(momz/1.5)) + .30*(100*math.tanh(accz/1.5)) + .15*(100*math.tanh(posz/1.5))
    return float(np.clip(idx,-100,100))


def support_v14(low, current_price):
    lo = np.asarray(low,dtype=float); cnt=len(lo)
    if cnt < SUPPORT_MIN_HISTORY or not np.isfinite(current_price): return np.nan,np.nan,np.nan,np.nan
    cp=[]; ca=[]; sw=SUPPORT_HALF_WINDOW
    for i in range(sw,cnt-sw):
        level=lo[i]
        if level < np.min(lo[i-sw:i]) and level < np.min(lo[i+1:i+sw+1]):
            age=cnt-(i+1)
            if age <= SUPPORT_MAX_AGE and level < current_price: cp.append(float(level)); ca.append(float(age))
    if not cp: return np.nan,np.nan,np.nan,np.nan
    cp=np.asarray(cp); ca=np.asarray(ca); centers=[]; strengths=[]; distances=[]
    for level in cp:
        mask=np.abs(cp/level-1)<=SUPPORT_GROUP_TOL; center=float(np.mean(cp[mask])); react=int(np.sum(mask)); recent=float(np.min(ca[mask])); dist=(current_price-center)/current_price
        rpts=min(react-1,SUPPORT_MAX_REACTIONS)*SUPPORT_POINTS_PER_REACTION; recpts=max(SUPPORT_RECENCY_MAX-recent*SUPPORT_RECENCY_DECAY,0); dpts=max(SUPPORT_PROXIMITY_MAX-dist*100,0)
        base=50 if recent<=20 else 30 if recent<=50 else 20
        centers.append(center); strengths.append(base+rpts+recpts+dpts); distances.append(dist)
    centers=np.asarray(centers); strengths=np.asarray(strengths); distances=np.asarray(distances); pos=int(np.argmax(strengths-distances))
    support=float(centers[pos]); dist=float(distances[pos]); strength=float(strengths[pos]); force='FORT' if strength>=70 else 'MOYEN' if strength>=45 else 'FAIBLE'
    if dist<=.02: score={'FORT':10,'MOYEN':8,'FAIBLE':6}[force]
    elif dist<=.04: score={'FORT':9,'MOYEN':7,'FAIBLE':5}[force]
    elif dist<=.06: score=5
    elif dist<=.10: score=2
    else: score=0
    return support,dist,float(score),strength


def rsi_points(r):
    if r < 20: return 55.0
    if r < 25: return 49.5
    if r < 30: return 47.3
    if r < 35: return 44.0
    if r < 37: return 33.0
    if r < 43: return 25.3
    if r <= 47: return 22.0
    if r <= 52: return 13.2
    if r <= 57: return 6.6
    if r <= 62: return 2.2
    return 0.0


def delta_rsi_points(dr):
    if dr >= 7: return 2.0
    if dr >= 5: return 5.0
    if dr >= 3: return 8.0
    if dr >= 2: return 12.0
    if dr >= .5: return 15.0
    if dr >= 0: return 10.0
    if dr >= -1.99: return 5.0
    if dr >= -3.99: return 2.0
    return 0.0


def rvol_points(rv):
    if rv < .7: return 0.0
    if rv < 1: return 4.0
    if rv < 1.25: return 8.0
    if rv < 1.5: return 14.0
    if rv < 2: return 20.0
    if rv < 2.5: return 15.0
    return 8.0


def trend_v14(close):
    c=np.asarray(close,dtype=float)
    if len(c)<TREND_SLOW+TREND_SLOPE_BACK: return 0.0
    p=float(c[-1]); maf=float(np.mean(c[-50:])); mas=float(np.mean(c[-200:])); mas0=float(np.mean(c[-220:-20])); up=mas>mas0; down=mas<mas0
    if p>maf and maf>mas and up: return 2.0
    if p<maf and p>mas and up: return 1.0
    if p<maf and maf<mas and down: return -2.0
    if p>maf and p<mas and down: return -1.0
    if p>mas and up: return .5
    if p<mas and down: return -.5
    return 0.0


def calc(row,h,cfg):
    h=restrict_v14_history(h)
    if len(h)<30: return None
    c=h['Close'].astype(float).to_numpy(); v=h['Volume'].astype(float).to_numpy(); low=h['Low'].astype(float).to_numpy(); price=float(c[-1])
    r,rp=wilder_rsi(c,int(cfg['indicators']['rsi_period']))
    if not np.isfinite(r) or not np.isfinite(rp): return None
    dr=r-rp; rvn=int(cfg['indicators']['rvol_period']); ref=v[-(rvn+1):-1] if len(v)>rvn else np.array([]); rvol=float(v[-1]/np.mean(ref)) if len(ref) and np.mean(ref)>0 else np.nan
    macd_idx=macd_v14(c); support,dist,support_score,support_strength=support_v14(low,price); trend=trend_v14(c)
    vc=c[-min(VOL_WINDOW,len(c)):]; ret=vc[1:]/vc[:-1]-1; vol_daily=sample_std(ret) if len(ret)>=2 else np.nan; vol_ann=vol_daily*math.sqrt(TRADING_DAYS) if np.isfinite(vol_daily) else np.nan
    rebound=rsi_points(r)+delta_rsi_points(dr)+(rvol_points(rvol) if np.isfinite(rvol) else 0)+(support_score if np.isfinite(support_score) else 0)
    timing_raw=float(np.clip(rebound+(macd_idx if np.isfinite(macd_idx) else 0)/100*10,0,100)); timing_corrected=float(np.clip(timing_raw*TREND_BUY_FACTORS.get(trend,1),0,100))
    f=cfg['filters']; checks={'rsi':(not f['rsi']['enabled']) or r<=f['rsi']['buy_max'],'reversal':(not f['reversal']['enabled']) or dr>=f['reversal']['min_delta'],'support':(not f['support']['enabled']) or (np.isfinite(dist) and dist<=f['support']['max_distance_pct']/100),'rvol':(not f['rvol']['enabled']) or (np.isfinite(rvol) and rvol>=f['rvol']['min']),'macd':(not f['macd']['enabled']) or (np.isfinite(macd_idx) and macd_idx>=f['macd']['min_momentum']),'trend':(not f['trend']['enabled']) or trend>=f['trend']['min']}
    return {'symbol':row['symbol'],'market':row['market'],'country':row['country'],'price':round(price,2),'rsi':round(r,1),'delta_rsi':round(dr,1),'rvol':round(rvol,2) if np.isfinite(rvol) else None,'support':round(support,2) if np.isfinite(support) else None,'support_distance_pct':round(dist*100,1) if np.isfinite(dist) else None,'support_score':round(support_score,1) if np.isfinite(support_score) else None,'support_strength':round(support_strength,1) if np.isfinite(support_strength) else None,'macd_momentum':round(macd_idx,1) if np.isfinite(macd_idx) else None,'trend':trend,'volatility_pct':round(vol_ann*100,1) if np.isfinite(vol_ann) else None,'timing_v14':round(timing_corrected,1),'filters':checks,'passed':all(checks.values()),'score':round(timing_corrected,1)}


def percentrank(values,x):
    a=np.sort(np.asarray([v for v in values if v is not None and np.isfinite(v)],dtype=float))
    if len(a)<2: return 0.0
    if x<=a[0]: return 0.0
    if x>=a[-1]: return 1.0
    i=int(np.searchsorted(a,x,'left'))
    if a[i]==x:
        lo=int(np.searchsorted(a,x,'left')); hi=int(np.searchsorted(a,x,'right'))-1
        return ((lo+hi)/2)/(len(a)-1)
    return ((i-1)+(x-a[i-1])/(a[i]-a[i-1]))/(len(a)-1)


def sell_signal(v):
    if v>=80: return 'VENTE FORTE'
    if v>=70: return 'VENTE'
    if v>=60: return 'SURVEILLER'
    if v>=50: return 'FAIBLE'
    return '--'


def main():
    cfg=json.loads((ROOT/'config/parameters.json').read_text(encoding='utf-8'))
    with open(ROOT/'config/symbols.csv',encoding='utf-8-sig') as f: rows=[r for r in csv.DictReader(f) if r.get('enabled','true').lower()=='true']
    with open(ROOT/'config/holdings.csv',encoding='utf-8-sig') as f: held={r['symbol'] for r in csv.DictReader(f) if r.get('symbol')}
    results=[]; errors=[]; failed_symbols=[]
    for i in range(0,len(rows),75):
        batch=rows[i:i+75]; tickers=[yahoo_symbol(r['symbol'],r['market']) for r in batch]
        try: raw=yf.download(tickers,period='2y',interval='1d',group_by='ticker',auto_adjust=True,threads=True,progress=False)
        except Exception as e: errors.append(str(e)); failed_symbols.extend(r['symbol'] for r in batch); continue
        for r,t in zip(batch,tickers):
            try:
                h=raw[t] if len(tickers)>1 else raw; x=calc(r,h,cfg)
                if x: results.append(x)
                else: failed_symbols.append(r['symbol'])
            except Exception as e: errors.append(f"{r['symbol']}: {e}"); failed_symbols.append(r['symbol'])
        time.sleep(1)
    buy=sorted([x for x in results if x['passed']],key=lambda x:x['score'],reverse=True)
    vols=[x['volatility_pct'] for x in results if x['volatility_pct'] is not None]
    sell=[]
    for x in results:
        if x['symbol'] not in held: continue
        r=x['rsi']; dr=x['delta_rsi']; rv=x['rvol']; ss=x['support_score']; macd=x['macd_momentum'] or 0.0; trend=x['trend']
        raw=rsi_points(100-r)+delta_rsi_points(-dr)+(rvol_points(rv) if rv is not None else 0)+((10-ss) if ss is not None else 0)
        timing=float(np.clip(raw-macd/100*10,0,100)); corrected=float(np.clip(timing*TREND_SELL_FACTORS.get(trend,1),0,100))
        potential=percentrank(vols,x['volatility_pct'])*100 if x['volatility_pct'] is not None else 0
        opportunity=corrected if corrected<50 else float(np.clip(corrected*.65+potential*.35,0,100))
        y=dict(x); y['sell_timing_v14']=round(corrected,1); y['potential_v14']=round(potential,1); y['sell_signal']=sell_signal(corrected); y['score']=round(opportunity,1); y['filters']={}; y['passed']=True; sell.append(y)
    sell.sort(key=lambda x:x['score'],reverse=True)
    out={'updated':datetime.now(timezone.utc).astimezone().strftime('%Y-%m-%d %H:%M'),'universe':len(rows),'analyzed':len(results),'errors':len(errors),'failed_symbols':sorted(set(failed_symbols)),'buy':buy[:cfg['visualisation']['buy_count']],'sell':sell[:cfg['visualisation']['sell_count']]}
    (ROOT/'data/results.json').write_text(json.dumps(out,ensure_ascii=False,indent=2),encoding='utf-8')
    print(f"Analyzed {len(results)}/{len(rows)}; buy={len(buy)} sell-ranked={len(sell)} errors={len(errors)} failed={len(set(failed_symbols))}")

if __name__=='__main__': main()
