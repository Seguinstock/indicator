import math
import numpy as np
import pandas as pd

def clip(x,a=-1,b=1): return float(np.clip(x,a,b))
def confidence(avail,total=50):
    p=100*avail/total if total else 0
    return "A" if p>66.7 else "B" if p>=33.3 else "C"
def atr(h,n=14):
    tr=pd.concat([(h.High-h.Low),(h.High-h.Close.shift()).abs(),(h.Low-h.Close.shift()).abs()],axis=1).max(axis=1)
    return float(tr.tail(n).mean())
def timing(h):
    h=h.dropna(subset=["Close"]); c=h.Close.astype(float); hi=h.High.astype(float); lo=h.Low.astype(float); p=float(c.iloc[-1]); a=atr(h)
    if not np.isfinite(a) or a<=1e-12:
        return 50.0,"C",{"location":0,"extension":0,"structure":0,"confirmation":0,"immediate":0},{"atr":None}
    sup=float(lo.tail(20).min()); res=float(hi.tail(60).max()); high52=float(hi.tail(252).max())
    d_sup=(p-sup)/a; d_res=(res-p)/a
    loc=clip((1.5-d_sup)/1.5)*.65+clip((d_res-1)/2)*.35
    ema=float(c.ewm(span=20,adjust=False).mean().iloc[-1]); ext=(p-ema)/a
    extension=clip((1.25-abs(ext))/1.75)
    r10=(float(hi.tail(10).max())-float(lo.tail(10).min()))/p
    prior=h.iloc[-40:-10]; r30=(float(prior.High.max())-float(prior.Low.min()))/float(prior.Close.iloc[-1]) if len(prior) else r10
    contraction=clip((r30-r10)/max(r30,1e-9)*2)
    pull=(p/float(hi.tail(20).max())-1)*100; pullq=1 if -8<=pull<=-1 else (0 if -12<=pull<=2 else -1)
    structure=.6*contraction+.4*pullq
    ret3=(p/float(c.iloc[-4])-1)*100 if len(c)>=4 else 0
    v=h.Volume.dropna(); vr=float(v.tail(3).mean()/v.iloc[-23:-3].mean()) if len(v)>=23 and v.iloc[-23:-3].mean()>0 else 1
    eligible=max(loc,structure)>.15
    confirmation=(clip(ret3/4)*.6+clip((vr-1))* .4) if eligible else 0
    gaps=(h.Open/h.Close.shift()-1).tail(3).abs()*100; gapmax=float(gaps.max()) if len(gaps) else 0
    immediate=-clip(max(gapmax-2,abs(ret3)-5)/8,0,1)
    parts={"location":15*loc,"extension":12*extension,"structure":10*structure,"confirmation":8*confirmation,"immediate":5*immediate}
    raw={"atr":round(a,3),"support20":round(sup,3),"resistance60":round(res,3),"high52":round(high52,3),"extension_atr":round(ext,2),"pullback20_pct":round(pull,2),"gap3_max_pct":round(gapmax,2)}
    return round(np.clip(50+sum(parts.values()),0,100),1),"A",{k:round(v,1) for k,v in parts.items()},raw

def risk(h,benchmark):
    h=h.dropna(subset=["Close"]); c=h.Close.astype(float); r=c.pct_change().dropna(); neg=r[r<0]
    downside=float(neg.std()*math.sqrt(252)) if len(neg)>10 else np.nan
    maxdd=abs(float((c/c.cummax()-1).min()))
    dv=(h.Close*h.Volume).dropna(); adv=float(dv.tail(60).median()) if len(dv) else np.nan
    gaps=(h.Open/h.Close.shift()-1).dropna(); neg_gap=abs(float(gaps.quantile(.02))) if len(gaps)>30 else np.nan
    aligned=pd.concat([r.rename("stock"),benchmark.rename("bench")],axis=1).dropna(); down=aligned[aligned.bench<0]; beta=np.nan
    if len(down)>=30 and float(down.bench.var())>0: beta=float(down.stock.cov(down.bench)/down.bench.var())
    parts={
      "downside_vol":14*(clip((downside-.20)/.35) if np.isfinite(downside) else 0),
      "drawdown":12*(clip((maxdd-.25)/.40) if np.isfinite(maxdd) else 0),
      "liquidity":10*(clip((6-math.log10(max(adv,1)))/2) if np.isfinite(adv) else 0),
      "gaps_history":7*(clip((neg_gap-.03)/.07) if np.isfinite(neg_gap) else 0),
      "market_sensitivity":4*(clip((beta-1)/.8) if np.isfinite(beta) else 0),
      "history":3*(-1 if len(c)>=450 else (0 if len(c)>=252 else 1))}
    avail=(14 if np.isfinite(downside) else 0)+(12 if np.isfinite(maxdd) else 0)+(10 if np.isfinite(adv) else 0)+(7 if np.isfinite(neg_gap) else 0)+(4 if np.isfinite(beta) else 0)+3
    raw={"downside_vol_pct":round(downside*100,1) if np.isfinite(downside) else None,"max_drawdown_pct":round(maxdd*100,1),"median_dollar_volume_60":round(adv) if np.isfinite(adv) else None,"bad_gap_p02_pct":round(neg_gap*100,1) if np.isfinite(neg_gap) else None,"downside_beta":round(beta,2) if np.isfinite(beta) else None}
    return round(np.clip(50+sum(parts.values()),0,100),1),confidence(avail),{k:round(v,1) for k,v in parts.items()},raw

def _statement(t,name,asof=None):
    try: df=getattr(t,name)
    except Exception: return pd.DataFrame()
    if df is None or df.empty:return pd.DataFrame()
    if asof is not None:
        keep=[]
        for col in df.columns:
            try:
                if pd.Timestamp(col).tz_localize(None)<=pd.Timestamp(asof).tz_localize(None):keep.append(col)
            except Exception: pass
        df=df[keep] if keep else pd.DataFrame()
    return df
def _first(df,names):
    if df is None or df.empty:return None
    for n in names:
        if n in df.index:
            x=pd.to_numeric(df.loc[n],errors="coerce").dropna()
            if len(x):return float(x.iloc[0])
    return None
def health(t,asof=None):
    bs=_statement(t,"quarterly_balance_sheet",asof); inc=_statement(t,"quarterly_income_stmt",asof); cf=_statement(t,"quarterly_cashflow",asof)
    cash=_first(bs,["Cash Cash Equivalents And Short Term Investments","Cash And Cash Equivalents"]); debt=_first(bs,["Total Debt"])
    equity=_first(bs,["Stockholders Equity","Total Equity Gross Minority Interest"]); assets=_first(bs,["Total Assets"])
    ca=_first(bs,["Current Assets"]); cl=_first(bs,["Current Liabilities"]); ebitda=_first(inc,["EBITDA","Normalized EBITDA"])
    rev=_first(inc,["Total Revenue"]); ni=_first(inc,["Net Income"]); fcf=_first(cf,["Free Cash Flow"])
    prerevenue=(rev is None or rev<=0) or (ebitda is not None and ebitda<0 and (rev is None or rev<5_000_000)); vals={}
    if debt is not None and cash is not None and ebitda not in (None,0) and not prerevenue: vals["solvency"]=clip((3-(debt-cash)/abs(ebitda))/3)
    elif prerevenue and debt is not None and cash is not None: vals["solvency"]=min(0.0,clip((cash-debt)/max(abs(cash),1)))
    if ca is not None and cl not in (None,0): vals["balance_liquidity"]=clip((ca/cl-1.2))
    if fcf is not None and rev not in (None,0) and not prerevenue: vals["cashflow"]=clip((fcf/rev-.03)/.10)
    elif prerevenue and fcf is not None and cash is not None and cash>0: vals["cashflow"]=0.0 if fcf>=0 else clip((cash/max(abs(fcf),1)-4)/4)
    if ni is not None and equity not in (None,0) and not prerevenue: vals["profitability"]=clip((ni/equity-.02)/.08)
    elif prerevenue and ni is not None: vals["profitability"]=-1.0 if ni<0 else 0.0
    if not inc.empty and "Total Revenue" in inc.index:
        rv=pd.to_numeric(inc.loc["Total Revenue"],errors="coerce").dropna()
        if len(rv)>=4 and abs(rv.mean())>0: vals["stability"]=clip((.30-float(rv.std()/abs(rv.mean())))/.25)
    if equity is not None and assets not in (None,0): vals["structural"]=clip((equity/assets-.25)/.35)
    weights={"solvency":13,"balance_liquidity":9,"cashflow":9,"profitability":7,"stability":5,"structural":7}
    parts={k:weights[k]*vals[k] if k in vals else 0 for k in weights}; avail=sum(weights[k] for k in vals)
    raw={"cash":cash,"debt":debt,"equity":equity,"assets":assets,"ebitda":ebitda,"revenue":rev,"free_cash_flow":fcf,"prerevenue_regime":prerevenue}
    return round(np.clip(50+sum(parts.values()),0,100),1),confidence(avail),{k:round(v,1) for k,v in parts.items()},raw
