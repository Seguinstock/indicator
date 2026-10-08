"""S1 : audit independant de sante financiere, 100 titres, donnees Yahoo annuelles.
Score exploratoire distinct de tout indicateur officiel Stockindicator.
"""
import json,math,time
from datetime import datetime,timezone
from pathlib import Path
import numpy as np
import pandas as pd
import yfinance as yf
from risk_memory_v2_100 import SYMBOLS

OUT=Path(__file__).parent
def series(df,names):
    if df is None or df.empty:return []
    lookup={str(k).lower():k for k in df.index}
    for name in names:
        if name.lower() in lookup:
            row=pd.to_numeric(df.loc[lookup[name.lower()]],errors="coerce")
            return [(str(pd.Timestamp(k).date()),float(v)) for k,v in row.items() if pd.notna(v) and np.isfinite(v)]
    return []
def latest(df,names):
    vals=series(df,names)
    return vals[0][1] if vals else None
def ratio(a,b):
    return a/b if a is not None and b is not None and b>0 else None
def clip(x):
    return max(0.,min(1.,x))
def score_metric(value,lo,hi,reverse=False):
    if value is None or not math.isfinite(value):return None
    z=clip((value-lo)/(hi-lo))
    return 100*(1-z if reverse else z)
def delta(vals):
    if len(vals)<2 or vals[1][1]<=0:return None
    return (vals[0][1]/vals[1][1]-1)*100
def run(sym,sector):
    t=yf.Ticker(sym)
    bs=t.balance_sheet; inc=t.income_stmt; cf=t.cashflow
    cash=latest(bs,["Cash Cash Equivalents And Short Term Investments","Cash And Cash Equivalents","Cash Financial"])
    debt=latest(bs,["Total Debt"])
    equity=latest(bs,["Stockholders Equity","Total Equity Gross Minority Interest"])
    assets=latest(bs,["Total Assets"])
    current_assets=latest(bs,["Current Assets"])
    current_liab=latest(bs,["Current Liabilities"])
    revenue=series(inc,["Total Revenue","Operating Revenue"])
    opinc=latest(inc,["Operating Income"])
    netinc=latest(inc,["Net Income","Net Income Common Stockholders"])
    ebitda=latest(inc,["EBITDA","Normalized EBITDA"])
    fcf=series(cf,["Free Cash Flow"])
    ocf=series(cf,["Operating Cash Flow","Total Cash From Operating Activities"])
    capex=series(cf,["Capital Expenditure"])
    # Fall back to OCF + signed capex (Yahoo capex usually negative).
    if not fcf and ocf and capex:
        cap_by_date=dict(capex)
        fcf=[(d,v+cap_by_date[d]) for d,v in ocf if d in cap_by_date]
    financial=sector=="financials"
    values={
      "revenue_growth_yoy_pct":delta(revenue),
      "fcf_growth_yoy_pct":delta(fcf),
      "fcf_margin_pct":100*ratio(fcf[0][1] if fcf else None,revenue[0][1] if revenue else None) if ratio(fcf[0][1] if fcf else None,revenue[0][1] if revenue else None) is not None else None,
      "operating_margin_pct":100*ratio(opinc,revenue[0][1] if revenue else None) if ratio(opinc,revenue[0][1] if revenue else None) is not None else None,
      "net_margin_pct":100*ratio(netinc,revenue[0][1] if revenue else None) if ratio(netinc,revenue[0][1] if revenue else None) is not None else None,
      "net_debt_to_ebitda":ratio((debt or 0)-(cash or 0),ebitda),
      "debt_to_equity":ratio(debt,equity),
      "equity_to_assets_pct":100*ratio(equity,assets) if ratio(equity,assets) is not None else None,
      "current_ratio":ratio(current_assets,current_liab),
      "fcf_positive_years":sum(v>0 for _,v in fcf[:4]) if fcf else None,
      "cash":cash,"debt":debt,"equity":equity,
      "revenue_years":revenue[:4],"fcf_years":fcf[:4]
    }
    # Sector-adapted exploratory metrics; banking leverage is not assessed with EBITDA.
    metrics={
       "revenue_growth":(score_metric(values["revenue_growth_yoy_pct"],-15,20),15),
       "profitability":(score_metric(values["net_margin_pct"] if financial else values["operating_margin_pct"],-10,25),20),
       "cash_generation":(score_metric(values["fcf_margin_pct"],-10,25),20 if not financial else 10),
       "cash_consistency":(score_metric(values["fcf_positive_years"],0,4),15 if not financial else 10),
       "capital_structure":(score_metric(values["equity_to_assets_pct"],3,15) if financial else score_metric(values["net_debt_to_ebitda"],0,5,True),30 if financial else 20),
       "liquidity":(None if financial else score_metric(values["current_ratio"],.6,2.0),0 if financial else 10),
       "profit_growth":(score_metric(values["fcf_growth_yoy_pct"],-50,50),15 if financial else 0)
    }
    available={k:(s,w) for k,(s,w) in metrics.items() if s is not None and w>0}
    weight=sum(w for _,w in available.values())
    # Do not rank poorly documented companies.
    health=round(sum(s*w for s,w in available.values())/weight,1) if weight>=65 else None
    return {"symbol":sym,"sector":sector,"score_s1":health,
            "coverage_weight":weight,"metrics":values,
            "component_scores":{k:round(s,1) for k,(s,w) in available.items()},
            "warnings":["Insufficient comparable fundamentals"] if health is None else [],
            "data_source":"Yahoo Finance annual statements; latest published years"}

def main():
    records=[]
    for i,(sym,sector) in enumerate(SYMBOLS,1):
        try:r=run(sym,sector)
        except Exception as e:r={"symbol":sym,"sector":sector,"score_s1":None,"error":str(e)[:250]}
        records.append(r)
        print(f"{i}/100 {sym}: {r.get('score_s1')} {r.get('error','')}",flush=True)
        time.sleep(1.3)
    ranked=sorted((r for r in records if r.get("score_s1") is not None),
                  key=lambda r:(-r["score_s1"],r["symbol"]))
    payload={"test":"S1","purpose":"independent exploratory financial health ranking",
             "generated_at":datetime.now(timezone.utc).isoformat(),
             "method":"annual statements, coverage-gated, sector-adapted exploratory score",
             "ranked_count":len(ranked),"total":len(records),
             "ranked":ranked,
             "unranked":[r for r in records if r.get("score_s1") is None]}
    (OUT/"s1_financial_health_100_results.json").write_text(json.dumps(payload,indent=2,ensure_ascii=False))
    lines=["# S1 — Audit indépendant de la santé financière","",
           f"Titres classés : {len(ranked)}/100. Source : Yahoo Finance, états annuels publiés.","",
           "Le score S1 est exploratoire et n'est PAS une formule officielle de Stockindicator.",
           "Les banques utilisent un critère de capitalisation distinct du levier dette/EBITDA.",
           "Données absentes : non classées si couverture pondérée inférieure à 65%.",
           "L'évolution concerne les années comptables publiées, pas l'évolution du cours.",
           "",
           "## Classement complet","",
           "| Rang | Titre | Secteur | S1 /100 | Croissance CA % | Marge % | Dette nette / EBITDA | FCF années positives |",
           "|---:|---|---|---:|---:|---:|---:|---:|"]
    fmt=lambda v: "n.d." if v is None else f"{v:.1f}"
    for i,r in enumerate(ranked,1):
        m=r["metrics"]
        lines.append(f"| {i} | {r['symbol']} | {r['sector']} | {fmt(r['score_s1'])} | {fmt(m['revenue_growth_yoy_pct'])} | {fmt(m['net_margin_pct'])} | {fmt(m['net_debt_to_ebitda'])} | {m['fcf_positive_years'] if m['fcf_positive_years'] is not None else 'n.d.'} |")
    lines.extend(["","## Titres non classés",""])
    for r in payload["unranked"]:lines.append(f"- {r['symbol']}: {r.get('error','données insuffisantes')}")
    lines.extend(["","## Limites de validation","",
      "Les états financiers gratuits peuvent comporter des retards, des valeurs manquantes ou des reclassements.",
      "Les ratios ne sont pas universellement comparables entre banques, assureurs, sociétés immobilières et industriels.",
      "La qualité d'un classement doit être validée par lecture de dossiers indépendants et comparaison des années publiées.",
      "Le test ne démontre ni la capacité prédictive du score ni la santé financière future."])
    (OUT/"s1_financial_health_100_report.md").write_text("\n".join(lines),encoding="utf-8")
    print(f"S1_READY ranked={len(ranked)} unranked={len(payload['unranked'])}",flush=True)
if __name__=="__main__":main()
