import json, math
from datetime import datetime, timezone
from pathlib import Path
import numpy as np, pandas as pd, yfinance as yf
import scanner
from relative_strength_runtime import relative_strength_score, market_return_20, _period_return

ROOT=Path(__file__).resolve().parents[1]
SAMPLE=[
("AAPL","XNYS","US"),("AMD","XNYS","US"),("AMZN","XNYS","US"),("BA","XNYS","US"),("BAC","XNYS","US"),
("CAT","XNYS","US"),("ADBE","XNYS","US"),("ABBV","XNYS","US"),("ABNB","XNYS","US"),("AVGO","XNYS","US"),
("AEM","XTSE","CA"),("AC","XTSE","CA"),("ATD","XTSE","CA"),("AQN","XTSE","CA"),("WSP","XTSE","CA"),
("WCP","XTSE","CA"),("WPM","XTSE","CA"),("ATZ","XTSE","CA"),("ACB","XTSE","CA"),("ATH","XTSE","CA"),
("ONE","XTSX","CA"),("EFF","XTSX","CA"),("AUMB","XTSX","CA"),("ACL","XTSX","CA"),("AIS","XTSX","CA"),
("AUAU","XTSX","CA"),("AME","XTSX","CA"),("ABA","XTSX","CA"),("ACDC","XTSX","CA"),("AAG","XTSX","CA")]
def clip(x,a=-1,b=1): return float(np.clip(x,a,b))
def conf(avail,total): 
    p=100*avail/total if total else 0
    return "A" if p>66.7 else "B" if p>=33.3 else "C"
def atr(h,n=14):
    tr=pd.concat([(h.High-h.Low),(h.High-h.Close.shift()).abs(),(h.Low-h.Close.shift()).abs()],axis=1).max(axis=1)
    return float(tr.tail(n).mean())
def timing(h):
    c=h.Close.dropna(); hi=h.High; lo=h.Low; p=float(c.iloc[-1]); a=atr(h)
    if not np.isfinite(a) or a <= 1e-12:
        parts={"location":0,"extension":0,"structure":0,"confirmation":0,"immediate":0}
        raw={"atr":round(a,6) if np.isfinite(a) else None,"support20":None,"resistance60":None,"high52":None,"extension_atr":None,"pullback20_pct":None,"gap3_max_pct":None}
        return 50.0, parts, raw, "C"
    # Location: 20d support/resistance + 52w high. Reward nearby support and useful overhead room.
    sup=float(lo.tail(20).min()); res=float(hi.tail(60).max()); high52=float(hi.tail(252).max())
    d_sup=(p-sup)/a if a>0 else np.nan; d_res=(res-p)/a if a>0 else np.nan
    loc=clip((1.5-d_sup)/1.5)*0.65 + clip((d_res-1.0)/2.0)*0.35
    # Extension: distance from 20d EMA in ATR; >2 ATR increasingly bad.
    ema=float(c.ewm(span=20,adjust=False).mean().iloc[-1]); ext=(p-ema)/a if a>0 else 0
    extension=clip((1.25-abs(ext))/1.75)
    # Structure: recent 10d range contraction vs prior 30d + controlled pullback from 20d high.
    r10=(float(hi.tail(10).max())-float(lo.tail(10).min()))/p
    prior=h.iloc[-40:-10]; r30=(float(prior.High.max())-float(prior.Low.min()))/float(prior.Close.iloc[-1]) if len(prior) else r10
    contraction=clip((r30-r10)/max(r30,1e-9)*2)
    pull=(p/float(hi.tail(20).max())-1)*100
    pullq=1 if -8<=pull<=-1 else (0 if -12<=pull<=2 else -1)
    structure=.6*contraction+.4*pullq
    # Confirmation ONLY after a favorable location/structure exists.
    ret3=(p/float(c.iloc[-4])-1)*100 if len(c)>=4 else 0
    v=h.Volume.dropna(); vr=float(v.tail(3).mean()/v.iloc[-23:-3].mean()) if len(v)>=23 and v.iloc[-23:-3].mean()>0 else 1
    eligible=max(loc,structure)>0.15
    confirmation=(clip(ret3/4)*.6+clip((vr-1)/1.0)*.4) if eligible else 0
    # Immediate 1-3 day gap/chase only.
    gaps=(h.Open/h.Close.shift()-1).tail(3).abs()*100
    gapmax=float(gaps.max()) if len(gaps) else 0
    ret3abs=abs(ret3)
    immediate=-clip(max(gapmax-2,ret3abs-5)/8,0,1)
    parts={"location":15*loc,"extension":12*extension,"structure":10*structure,"confirmation":8*confirmation,"immediate":5*immediate}
    return round(np.clip(50+sum(parts.values()),0,100),1),{k:round(v,1) for k,v in parts.items()},{"atr":round(a,3),"support20":round(sup,3),"resistance60":round(res,3),"high52":round(high52,3),"extension_atr":round(ext,2),"pullback20_pct":round(pull,2),"gap3_max_pct":round(gapmax,2)},"A"
def risk(h, benchmark):
    c=h.Close.dropna(); r=c.pct_change().dropna(); neg=r[r<0]
    downside=float(neg.std()*math.sqrt(252)) if len(neg)>10 else np.nan
    rollmax=c.cummax(); dd=(c/rollmax-1); maxdd=abs(float(dd.min()))
    dv=(h.Close*h.Volume).dropna(); adv=float(dv.tail(60).median()) if len(dv) else np.nan
    gaps=(h.Open/h.Close.shift()-1).dropna(); neg_gap=abs(float(gaps.quantile(.02))) if len(gaps)>30 else np.nan
    s_down=clip((downside-.20)/.35) if np.isfinite(downside) else 0
    s_dd=clip((maxdd-.25)/.40) if np.isfinite(maxdd) else 0
    s_liq=clip((6-math.log10(max(adv,1)))/2) if np.isfinite(adv) else 0
    s_gap=clip((neg_gap-.03)/.07) if np.isfinite(neg_gap) else 0
    aligned=pd.concat([r.rename("stock"),benchmark.rename("bench")],axis=1).dropna()
    down=aligned[aligned.bench<0]; beta_down=np.nan
    if len(down)>=30 and float(down.bench.var())>0:
        beta_down=float(down.stock.cov(down.bench)/down.bench.var())
    s_beta=clip((beta_down-1.0)/0.8) if np.isfinite(beta_down) else 0
    s_hist=-1 if len(c)>=450 else (0 if len(c)>=252 else 1)
    parts={"downside_vol":14*s_down,"drawdown":12*s_dd,"liquidity":10*s_liq,"gaps_history":7*s_gap,"market_sensitivity":4*s_beta,"history":3*s_hist}
    available=14+12+10+7+3+(4 if np.isfinite(beta_down) else 0)
    raw={"downside_vol_pct":round(downside*100,1) if np.isfinite(downside) else None,"max_drawdown_pct":round(maxdd*100,1),"median_dollar_volume_60":round(adv) if np.isfinite(adv) else None,"bad_gap_p02_pct":round(neg_gap*100,1) if np.isfinite(neg_gap) else None,"downside_beta":round(beta_down,2) if np.isfinite(beta_down) else None}
    return round(np.clip(50+sum(parts.values()),0,100),1),conf(available,50),{k:round(v,1) for k,v in parts.items()},raw
def firstval(df,names):
    if df is None or df.empty:return None
    for n in names:
        if n in df.index:
            x=pd.to_numeric(df.loc[n],errors="coerce").dropna()
            if len(x): return float(x.iloc[0])
    return None
def health(t):
    try: bs=t.quarterly_balance_sheet
    except: bs=pd.DataFrame()
    try: inc=t.quarterly_income_stmt
    except: inc=pd.DataFrame()
    try: cf=t.quarterly_cashflow
    except: cf=pd.DataFrame()
    cash=firstval(bs,["Cash Cash Equivalents And Short Term Investments","Cash And Cash Equivalents"])
    debt=firstval(bs,["Total Debt"])
    equity=firstval(bs,["Stockholders Equity","Total Equity Gross Minority Interest"])
    assets=firstval(bs,["Total Assets"])
    curA=firstval(bs,["Current Assets"]); curL=firstval(bs,["Current Liabilities"])
    ebitda=firstval(inc,["EBITDA","Normalized EBITDA"])
    rev=firstval(inc,["Total Revenue"])
    ni=firstval(inc,["Net Income"])
    fcf=firstval(cf,["Free Cash Flow"])
    # Six fixed families; missing = zero displacement, never redistributed.
    prerevenue=(rev is None or rev <= 0) or (ebitda is not None and ebitda < 0 and (rev is None or rev < 5_000_000))
    vals={}
    if debt is not None and cash is not None and ebitda not in (None,0) and not prerevenue:
        nde=(debt-cash)/abs(ebitda); vals["solvency"]=clip((3-nde)/3)
    elif prerevenue and debt is not None and cash is not None:
        vals["solvency"]=min(0.0, clip((cash-debt)/max(abs(cash),1)))
    if curA is not None and curL not in (None,0):
        cr=curA/curL; vals["balance_liquidity"]=clip((cr-1.2)/1.0)
    if fcf is not None and rev not in (None,0) and not prerevenue: vals["cashflow"]=clip((fcf/rev-.03)/.10)
    elif prerevenue and fcf is not None and cash is not None and cash>0:
        # Approximate quarterly cash runway from current FCF burn. Positive FCF is neutral here.
        vals["cashflow"]=0.0 if fcf>=0 else clip((cash/max(abs(fcf),1)-4)/4)
    if ni is not None and equity not in (None,0) and not prerevenue: vals["profitability"]=clip((ni/equity-.02)/.08)
    elif prerevenue and ni is not None: vals["profitability"]=-1.0 if ni<0 else 0.0
    # Stability needs history: quarterly revenue coefficient of variation (lower better)
    if inc is not None and not inc.empty and "Total Revenue" in inc.index:
        rv=pd.to_numeric(inc.loc["Total Revenue"],errors="coerce").dropna()
        if len(rv)>=4 and abs(rv.mean())>0: vals["stability"]=clip((.30-float(rv.std()/abs(rv.mean())))/.25)
    # Structural robustness: equity/assets only; no stock-market liquidity.
    if equity is not None and assets not in (None,0): vals["structural"]=clip(((equity/assets)-.25)/.35)
    weights={"solvency":13,"balance_liquidity":9,"cashflow":9,"profitability":7,"stability":5,"structural":7}
    parts={k:(weights[k]*vals[k] if k in vals else 0) for k in weights}; av=sum(weights[k] for k in vals)
    raw={"cash":cash,"debt":debt,"equity":equity,"assets":assets,"ebitda":ebitda,"revenue":rev,"free_cash_flow":fcf,"prerevenue_regime":prerevenue}
    return round(np.clip(50+sum(parts.values()),0,100),1),conf(av,50),{k:round(v,1) for k,v in parts.items()}, {k:(round(v,2) if v is not None else None) for k,v in raw.items()}
def main():
    cfg=json.loads((ROOT/"config/parameters.json").read_text())
    mkt,_=market_return_20(); out=[]; errors=[]
    bench=yf.download("^GSPC",period="2y",interval="1d",auto_adjust=True,progress=False)
    if isinstance(bench.columns,pd.MultiIndex): bench.columns=bench.columns.get_level_values(0)
    bench_ret=bench.Close.dropna().astype(float).pct_change().dropna()
    for sym,market,country in SAMPLE:
        y=scanner.yahoo_symbol(sym,market)
        try:
            h=yf.download(y,period="2y",interval="1d",auto_adjust=True,progress=False)
            if isinstance(h.columns,pd.MultiIndex): h.columns=h.columns.get_level_values(0)
            h=h.dropna(subset=["Close"])
            if len(h)<80: raise ValueError("insufficient price history")
            row={"symbol":sym,"market":market,"country":country}
            base=scanner.calc(row,h,cfg)
            c=h.Close.dropna().astype(float); ret20=_period_return(c,20); ret60=_period_return(c,60)
            score,comp=relative_strength_score(base["rsi"],base["rvol"],base["trend"],ret20,ret60,ret20-mkt,cfg)
            ti,tip,ti_raw,tc=timing(h); ri,rc,rip,ri_raw=risk(h,bench_ret); he,hc,hep,he_raw=health(yf.Ticker(y))
            out.append({"symbol":sym,"market":market,"yahoo":y,"score":round(score,1),"timing":ti,"timing_confidence":tc,"risk":ri,"risk_confidence":rc,"health":he,"health_confidence":hc,"components":{"score":comp,"timing":tip,"risk":rip,"health":hep},"raw":{"timing":ti_raw,"risk":ri_raw,"health":he_raw}})
            print(sym,round(score,1),ti,ri,he,hc)
        except Exception as e: errors.append({"symbol":sym,"error":str(e)}); print("ERROR",sym,e)
    if len(out) != len(SAMPLE) or errors:
        raise RuntimeError(f"QA FAILED: completed={len(out)}/{len(SAMPLE)}, errors={len(errors)}; {errors[:3]}")
    for x in out:
        for key in ("score","timing","risk","health"):
            if not np.isfinite(float(x[key])):
                raise RuntimeError("QA FAILED: non-finite result")
        if any(x[k] not in ("A","B","C") for k in ("timing_confidence","risk_confidence","health_confidence")):
            raise RuntimeError("QA FAILED: invalid confidence")
    # correlations only as diagnostic, never part of scores
    df=pd.DataFrame(out)
    corr=df[["score","timing","risk","health"]].corr().round(3).to_dict() if len(df)>=4 else {}
    payload={"generated_at":datetime.now(timezone.utc).isoformat(),"status":"EXPERIMENTAL V2 - ATR zero handling + prerevenue health + downside beta; no production formula changed","sample_target":30,"completed":len(out),"errors":errors,"correlations":corr,"results":out}
    (ROOT/"data/filter_pilot_30.json").write_text(json.dumps(payload,ensure_ascii=False,indent=2),encoding="utf-8")
if __name__=="__main__": main()
