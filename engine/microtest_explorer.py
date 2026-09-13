import json, os, random, time
from datetime import datetime, timezone
from pathlib import Path
import numpy as np
import pandas as pd
import yfinance as yf
import scanner

ROOT=Path(__file__).resolve().parents[1]
SEED=int(os.environ.get('MICROTEST_SEED','20260910'))
N_PERIODS=int(os.environ.get('MICROTEST_PERIODS','8'))
HORIZONS=[10,20,30,50,75,100]
TOP_NS=[10,30,100]
START_MIN=pd.Timestamp('2021-04-01'); START_MAX=pd.Timestamp('2026-05-15')

def clip(x): return float(np.clip(x,0,1))
def finite(x,d=0): return float(x) if x is not None and np.isfinite(x) else d
def qtrend(t): return scanner.TREND_POTENTIAL.get(float(t),.5)
def qrsi(r,t,w): return clip(1-abs(finite(r,50)-t)/w)
def qrvol(v,lo=.6,hi=2): return clip((finite(v,0)-lo)/(hi-lo))
def qsupport(v,m=8): return .5 if v is None or not np.isfinite(v) else clip((m-float(v))/m)
def qlowvol(v,lo=15,hi=60): return 1-clip((finite(v,100)-lo)/(hi-lo))
def qmacdpos(v): return clip(finite(v,0)/60)
def qmacdlow(v): return clip(-finite(v,0)/60) if finite(v,0)<0 else 0
def qrebound(v,lo=-2,hi=4): return clip((finite(v,0)-lo)/(hi-lo))
def weighted(parts):
    z=sum(w for _,w in parts); return 100*sum(q*w for q,w in parts)/z

def score_family(name,x,extra):
    rsi=x['rsi']; dr=x['delta_rsi']; rv=x['rvol']; tr=x['trend']; vol=x['volatility_pct']; mac=x['macd_momentum']; sup=x['support_distance_pct']
    ret20=extra.get('ret20',0); ret60=extra.get('ret60',0); rel20=extra.get('rel20',0); near_high=extra.get('near_high',0)
    if name=='momentum': return weighted([(qtrend(tr),30),(qmacdpos(mac),25),(clip((rsi-45)/25),15),(clip((ret20+5)/20),20),(qrvol(rv),10)])
    if name=='momentum_pullback': return weighted([(qtrend(tr),35),(clip((ret60+5)/25),20),(qrsi(rsi,42,18),20),(qsupport(sup,10),10),(qrebound(dr),10),(qrvol(rv),5)])
    if name=='breakout': return weighted([(clip((near_high-.90)/.10),35),(qrvol(rv,.8,2.2),25),(qtrend(tr),20),(qmacdpos(mac),10),(clip((ret20+3)/15),10)])
    if name=='mean_reversion': return weighted([(clip((40-rsi)/20),35),(clip((-ret20)/18),25),(qrebound(dr),20),(qsupport(sup,10),10),(qtrend(tr),10)])
    if name=='lowvol_trend': return weighted([(qlowvol(vol),40),(qtrend(tr),40),(qrsi(rsi,50,25),10),(qrvol(rv,.4,1.5),10)])
    if name=='acceleration': return weighted([(qrebound(dr,-1,5),30),(qmacdpos(mac),25),(clip((ret20+5)/20),20),(qtrend(tr),15),(qrvol(rv),10)])
    if name=='relative_strength': return weighted([(clip((rel20+5)/20),40),(clip((ret60+5)/30),25),(qtrend(tr),20),(qrvol(rv),10),(qrsi(rsi,58,22),5)])
    if name=='relative_contrarian': return weighted([(qtrend(tr),30),(clip((ret60+5)/30),25),(clip((-rel20+3)/15),20),(qrsi(rsi,38,18),15),(qrebound(dr),10)])
    if name=='low_macd': return weighted([(qmacdlow(mac),50),(qtrend(tr),20),(qrsi(rsi,33,20),15),(qrvol(rv),10),(qsupport(sup,10),5)])
    if name=='defensive': return weighted([(qtrend(tr),40),(qlowvol(vol),30),(qsupport(sup,8),15),(qrsi(rsi,40,20),10),(qrvol(rv,.6,1.8),5)])
    return 0

FAMILIES=['momentum','momentum_pullback','breakout','mean_reversion','lowvol_trend','acceleration','relative_strength','relative_contrarian','low_macd','defensive']

def pick_periods():
    c=list(pd.bdate_range(START_MIN,START_MAX)); random.Random(SEED).shuffle(c); out=[]
    for d in c:
        if all(abs((d-x).days)>=120 for x in out): out.append(d)
        if len(out)>=N_PERIODS: break
    return sorted(out)

def pit_rows(asof):
    import pitindex
    m=pitindex.get_constituents(asof.strftime('%Y-%m-%d'),index='sp1500'); seen=set(); out=[]
    for t in m['ticker'].tolist():
        s=str(t).strip().upper().replace('.','-')
        if s and s not in seen: seen.add(s); out.append({'symbol':s,'market':'XNYS','country':'US','enabled':'true'})
    return out

def normalize_idx(h):
    if h is None or h.empty:
        return pd.DataFrame()
    h=h.copy()
    if isinstance(h.columns,pd.MultiIndex):
        levels=[list(h.columns.get_level_values(i)) for i in range(h.columns.nlevels)]
        if 'Close' in levels[0]: h.columns=h.columns.get_level_values(0)
        elif h.columns.nlevels>1 and 'Close' in levels[1]: h.columns=h.columns.get_level_values(1)
    if 'Close' not in h.columns:
        return pd.DataFrame()
    h=h.dropna(subset=['Close']).copy(); idx=pd.to_datetime(h.index)
    if getattr(idx,'tz',None): idx=idx.tz_localize(None)
    h.index=idx; return h

def features(row,h,cfg,asof):
    h=normalize_idx(h)
    if h.empty:return None
    hist=h.loc[h.index<=asof].copy()
    if len(hist)<80:return None
    old=scanner.restrict_v14_history
    scanner.restrict_v14_history=lambda z: normalize_idx(z).loc[(normalize_idx(z).index<=asof)&(normalize_idx(z).index>=asof-pd.Timedelta(days=scanner.HISTORY_DAYS))].copy()
    try: x=scanner.calc(row,h,cfg)
    finally: scanner.restrict_v14_history=old
    if not x:return None
    c=hist['Close'].astype(float); entry=float(c.iloc[-1])
    ret20=(entry/float(c.iloc[-21])-1)*100 if len(c)>21 else 0
    ret60=(entry/float(c.iloc[-61])-1)*100 if len(c)>61 else ret20
    hi60=float(hist['High'].astype(float).tail(60).max()); near=entry/hi60 if hi60 else 0
    return x,entry,{'ret20':ret20,'ret60':ret60,'near_high':near}

def daily_momentum(close):
    s=pd.Series(close,dtype=float)
    if len(s)<16:return 0,50
    d=s.diff(); up=d.clip(lower=0).rolling(14).mean(); dn=(-d.clip(upper=0)).rolling(14).mean(); rs=up/dn.replace(0,np.nan); rsi=(100-100/(1+rs)).iloc[-1]
    e12=s.ewm(span=12,adjust=False).mean(); e26=s.ewm(span=26,adjust=False).mean(); mac=(e12-e26); sig=mac.ewm(span=9,adjust=False).mean(); mom=float((mac-sig).iloc[-1])
    return mom, finite(rsi,50)

def simulate(h,asof,horizon,entry,rule):
    h=normalize_idx(h)
    if h.empty:return None
    f=h.loc[h.index>asof].head(horizon)
    if f.empty:return None
    peak=entry; peak_gain=0; exit_px=None; exit_i=None; reason='horizon'
    closes=[]
    for i,(_,r) in enumerate(f.iterrows(),1):
        px=float(r['Close']); peak=max(peak,float(r['High']),px); peak_gain=max(peak_gain,(peak/entry-1)*100); closes.append(px)
        dd=(px/peak-1)*100
        mom,rsi=daily_momentum(([entry]*30)+closes)
        deteriorating=(mom<0 and rsi<48) or (len(closes)>=3 and closes[-1]<closes[-2]<closes[-3])
        trigger=False
        if rule=='trail5': trigger=dd<=-5
        elif rule=='trail8': trigger=dd<=-8
        elif rule=='trail12': trigger=dd<=-12
        elif rule=='armed10_5': trigger=peak_gain>=10 and dd<=-5
        elif rule=='armed15_8': trigger=peak_gain>=15 and dd<=-8
        elif rule=='surge10_5_tech': trigger=peak_gain>=10 and dd<=-5 and deteriorating
        elif rule=='surge15_6_tech': trigger=peak_gain>=15 and dd<=-6 and deteriorating
        elif rule=='surge20_8_tech': trigger=peak_gain>=20 and dd<=-8 and deteriorating
        if trigger: exit_px=px; exit_i=i; reason=rule; break
    if exit_px is None: exit_px=float(f['Close'].iloc[-1]); exit_i=len(f)
    final=float(f['Close'].iloc[-1]); ret=(exit_px/entry-1)*100; best=(peak/entry-1)*100
    return {'return_pct':ret,'days':exit_i,'best_gain_pct':best,'giveback_pct':best-ret,'post_exit_pct':(final/exit_px-1)*100,'reason':reason}

RULES=['fixed','trail5','trail8','trail12','armed10_5','armed15_8','surge10_5_tech','surge15_6_tech','surge20_8_tech']

def benchmark(asof,horizon):
    start=(asof-pd.Timedelta(days=10)).strftime('%Y-%m-%d')
    end=(asof+pd.Timedelta(days=160)).strftime('%Y-%m-%d')
    for symbol in ('^SP1500','^GSPC'):
        try:
            h=yf.download(symbol,start=start,end=end,auto_adjust=True,progress=False)
            h=normalize_idx(h)
            if h.empty: continue
            c=h['Close']; c=c.iloc[:,0] if isinstance(c,pd.DataFrame) else c
            b=c.loc[c.index<=asof]; a=c.loc[c.index>asof].head(horizon)
            if len(b) and len(a): return float((a.iloc[-1]/b.iloc[-1]-1)*100)
        except Exception:
            continue
    return None

def main():
    cfg=json.loads((ROOT/'config/parameters.json').read_text()); periods=[]
    for pi,asof in enumerate(pick_periods(),1):
        rows=pit_rows(asof); ds=(asof-pd.Timedelta(days=650)).strftime('%Y-%m-%d'); de=(asof+pd.Timedelta(days=170)).strftime('%Y-%m-%d'); recs=[]
        market20=benchmark(asof,20) or 0
        for j in range(0,len(rows),75):
            batch=rows[j:j+75]; ticks=[scanner.yahoo_symbol(r['symbol'],r['market']) for r in batch]
            try: raw=yf.download(ticks,start=ds,end=de,group_by='ticker',auto_adjust=True,threads=True,progress=False)
            except Exception: continue
            for row,t in zip(batch,ticks):
                try:
                    h=raw[t] if len(ticks)>1 else raw; z=features(row,h,cfg,asof)
                    if not z:continue
                    x,entry,extra=z; extra['rel20']=extra['ret20']-market20
                    scores={f:score_family(f,x,extra) for f in FAMILIES}; recs.append((row['symbol'],entry,h,scores))
                except Exception: pass
            time.sleep(.15)
        result={};
        for horizon in HORIZONS:
            b=benchmark(asof,horizon); result[str(horizon)]={'benchmark':b,'families':{}}
            for fam in FAMILIES:
                ranked=sorted(recs,key=lambda z:z[3][fam],reverse=True)
                result[str(horizon)]['families'][fam]={}
                for n in TOP_NS:
                    chosen=ranked[:n]; rr={rule:[] for rule in RULES}
                    for sym,entry,h,scores in chosen:
                        fixed=simulate(h,asof,horizon,entry,'none')
                        if fixed:
                            rr['fixed'].append(fixed)
                            for rule in RULES[1:]:
                                s=simulate(h,asof,horizon,entry,rule)
                                if s: rr[rule].append(s)
                    result[str(horizon)]['families'][fam][str(n)]={rule:{'n':len(v),'avg_return_pct':round(float(np.mean([x['return_pct'] for x in v])),3) if v else None,'median_return_pct':round(float(np.median([x['return_pct'] for x in v])),3) if v else None,'avg_days':round(float(np.mean([x['days'] for x in v])),1) if v else None,'avg_best_gain_pct':round(float(np.mean([x['best_gain_pct'] for x in v])),3) if v else None,'avg_giveback_pct':round(float(np.mean([x['giveback_pct'] for x in v])),3) if v else None,'avg_post_exit_pct':round(float(np.mean([x['post_exit_pct'] for x in v])),3) if v else None} for rule,v in rr.items()}
        periods.append({'period':pi,'asof':str(asof.date()),'tested':len(recs),'results':result}); print(f'{pi}/{N_PERIODS} {asof.date()} tested={len(recs)}')
    combos={}
    for h in HORIZONS:
      for fam in FAMILIES:
       for n in TOP_NS:
        for rule in RULES:
         vals=[]; benches=[]
         for p in periods:
          z=p['results'][str(h)]['families'][fam][str(n)][rule]; b=p['results'][str(h)]['benchmark']
          if z['avg_return_pct'] is not None and b is not None: vals.append(z['avg_return_pct']); benches.append(b)
         if vals:
          ex=np.array(vals)-np.array(benches); combos[f'{fam}|{h}|{n}|{rule}']={'avg_return_pct':round(float(np.mean(vals)),3),'median_return_pct':round(float(np.median(vals)),3),'avg_benchmark_pct':round(float(np.mean(benches)),3),'avg_excess_pct':round(float(np.mean(ex)),3),'beat_periods':int(np.sum(ex>0)),'periods':len(vals)}
    leaders=sorted(combos.items(),key=lambda kv:(kv[1]['avg_excess_pct'],kv[1]['beat_periods']),reverse=True)[:100]
    out={'generated':datetime.now(timezone.utc).isoformat(),'seed':SEED,'periods':N_PERIODS,'horizons':HORIZONS,'top_ns':TOP_NS,'families':FAMILIES,'exit_rules':RULES,'leaders':[{'combination':k,**v} for k,v in leaders],'period_results':periods}
    (ROOT/'data/microtest_explorer.json').write_text(json.dumps(out,ensure_ascii=False,indent=2)); print(json.dumps(out['leaders'][:20],indent=2))

def run_requested_mode():
    request_path=ROOT/'data'/'microtest_strategy24_request.json'
    if request_path.exists():
        request=json.loads(request_path.read_text())
        if request.get('mode')=='strategy24':
            strategy=str(request.get('strategy','')).strip().lower()
            if strategy not in ('breakout','momentum','relative_strength'):
                raise ValueError(f'Unsupported strategy24 request: {strategy}')
            os.environ['MICROTEST_STRATEGY']=strategy
            import microtest_strategy24
            microtest_strategy24.main()
            return
    main()

if __name__=='__main__': run_requested_mode()