import csv, json, math, time
from datetime import datetime, timezone
from pathlib import Path
import numpy as np
import pandas as pd
import yfinance as yf

ROOT=Path(__file__).resolve().parents[1]

def yahoo_symbol(symbol, market):
    s=symbol.replace('.', '-')
    if market=='XTSE': return s+'.TO'
    if market=='XTSX': return s+'.V'
    if market=='XCNQ': return s+'.CN'
    return s

def ema(s,n): return s.ewm(span=n,adjust=False).mean()

def calc(row, h, cfg):
    h=h.dropna(subset=['Close']).copy()
    if len(h)<220: return None
    c=h['Close'].astype(float); v=h['Volume'].astype(float)
    d=c.diff(); up=d.clip(lower=0); dn=(-d.clip(upper=0))
    n=cfg['indicators']['rsi_period']; au=up.ewm(alpha=1/n,adjust=False).mean(); ad=dn.ewm(alpha=1/n,adjust=False).mean()
    rsi=100-(100/(1+au/ad.replace(0,np.nan))); r=float(rsi.iloc[-1]); rp=float(rsi.iloc[-2]); dr=r-rp
    rvn=cfg['indicators']['rvol_period']; rvol=float(v.iloc[-1]/v.iloc[-rvn:].mean()) if v.iloc[-rvn:].mean()>0 else np.nan
    fast=ema(c,12); slow=ema(c,26); macd=fast-slow; sig=ema(macd,9); hist=macd-sig
    scale=float(hist.tail(20).abs().max()) or 1.0
    macd_mom=float(np.clip((0.55*(hist.iloc[-1]-hist.iloc[-2])+0.30*((hist.iloc[-1]-hist.iloc[-2])-(hist.iloc[-2]-hist.iloc[-3]))+0.15*hist.iloc[-1])/scale*100,-100,100))
    lows=h['Low'].astype(float).tail(cfg['indicators']['support_lookback'])
    support=float(lows.rolling(7,center=True).min().dropna().tail(80).quantile(.65)) if len(lows)>20 else float(lows.min())
    price=float(c.iloc[-1]); support=min(support,price); dist=(price-support)/price if price else np.nan
    ma50=float(c.tail(50).mean()); ma200=float(c.tail(200).mean()); ma200old=float(c.iloc[-220:-20].tail(200).mean())
    slope=ma200>ma200old
    trend=2 if price>ma50>ma200 and slope else (1 if price<ma50 and price>ma200 and slope else (-2 if price<ma50<ma200 and not slope else (-1 if price>ma50 and price<ma200 and not slope else (0.5 if price>ma200 and slope else (-0.5 if price<ma200 and not slope else 0)))))
    vol=float(c.pct_change().tail(252).std()*math.sqrt(252))
    f=cfg['filters']
    checks={
      'rsi': (not f['rsi']['enabled']) or r<=f['rsi']['buy_max'],
      'reversal': (not f['reversal']['enabled']) or dr>=f['reversal']['min_delta'],
      'support': (not f['support']['enabled']) or dist<=f['support']['max_distance_pct']/100,
      'rvol': (not f['rvol']['enabled']) or rvol>=f['rvol']['min'],
      'macd': (not f['macd']['enabled']) or macd_mom>=f['macd']['min_momentum'],
      'trend': (not f['trend']['enabled']) or trend>=f['trend']['min']}
    passed=all(checks.values())
    # Rang uniquement entre les titres qui ont déjà passé les filtres; il ne peut compenser un échec.
    rank=float(np.clip((100-r)*.35 + max(dr,0)*3 + max(0,1-dist*10)*20 + min(rvol,2.5)*8 + max(macd_mom,0)*.15,0,100))
    return {'symbol':row['symbol'],'market':row['market'],'country':row['country'],'price':round(price,2),'rsi':round(r,1),'delta_rsi':round(dr,1),'rvol':round(rvol,2),'support':round(support,2),'support_distance_pct':round(dist*100,1),'macd_momentum':round(macd_mom,1),'trend':trend,'volatility_pct':round(vol*100,1),'filters':checks,'passed':passed,'score':round(rank,1)}

def main():
    cfg=json.loads((ROOT/'config/parameters.json').read_text(encoding='utf-8'))
    with open(ROOT/'config/symbols.csv',encoding='utf-8-sig') as f: rows=[r for r in csv.DictReader(f) if r.get('enabled','true').lower()=='true']
    with open(ROOT/'config/holdings.csv',encoding='utf-8-sig') as f: held={r['symbol'] for r in csv.DictReader(f) if r.get('symbol')}
    results=[]; errors=[]
    for i in range(0,len(rows),75):
        batch=rows[i:i+75]; tickers=[yahoo_symbol(r['symbol'],r['market']) for r in batch]
        try: raw=yf.download(tickers,period='3y',interval='1d',group_by='ticker',auto_adjust=True,threads=True,progress=False)
        except Exception as e: errors.append(str(e)); continue
        for r,t in zip(batch,tickers):
            try:
                h=raw[t] if len(tickers)>1 else raw
                x=calc(r,h,cfg)
                if x: results.append(x)
            except Exception as e: errors.append(f"{r['symbol']}: {e}")
        time.sleep(1)
    buy=sorted([x for x in results if x['passed']],key=lambda x:x['score'],reverse=True)
    sell=[]
    for x in results:
        if x['symbol'] not in held: continue
        sell_checks={'rsi':x['rsi']>=cfg['filters']['sell']['rsi_min'],'macd':x['macd_momentum']<=cfg['filters']['sell']['macd_max'],'trend':x['trend']<=cfg['filters']['sell']['trend_max']}
        y=dict(x); y['filters']=sell_checks; y['passed']=all(sell_checks.values()); y['score']=round(min(100,x['rsi']*.55+max(0,-x['macd_momentum'])*.3+max(0,-x['trend'])*10),1)
        if y['passed']: sell.append(y)
    sell.sort(key=lambda x:x['score'],reverse=True)
    out={'updated':datetime.now(timezone.utc).astimezone().strftime('%Y-%m-%d %H:%M'),'universe':len(rows),'analyzed':len(results),'errors':len(errors),'buy':buy[:cfg['visualisation']['buy_count']],'sell':sell[:cfg['visualisation']['sell_count']]}
    (ROOT/'data/results.json').write_text(json.dumps(out,ensure_ascii=False,indent=2),encoding='utf-8')
    print(f"Analyzed {len(results)}/{len(rows)}; buy={len(buy)} sell={len(sell)} errors={len(errors)}")

if __name__=='__main__': main()
