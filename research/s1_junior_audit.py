"""Audit S1 ciblé sur juniors TSXV : mêmes champs Yahoo, sans changer le score officiel."""
import csv,json,random,time
from datetime import datetime,timezone
from pathlib import Path
from s1_financial_health_100 import run

ROOT=Path(__file__).resolve().parents[1]
OUT=Path(__file__).parent
def num(v):
    return v if isinstance(v,(int,float)) else None
def classify(r):
    m=r.get("metrics") or {}
    rev=m.get("revenue_years") or []
    fcf=m.get("fcf_years") or []
    debt=num(m.get("debt"))
    cash=num(m.get("cash"))
    revenue=rev[0][1] if rev else None
    fcf_now=fcf[0][1] if fcf else None
    no_revenue=(revenue is not None and revenue<=0)
    debt_cash=(debt/cash if cash is not None and cash>0 and debt is not None else None)
    flags=[]
    if no_revenue:flags.append("zero_reported_revenue")
    if revenue is None:flags.append("revenue_missing")
    if debt is not None and debt>0 and (cash is None or cash<=0):flags.append("debt_without_reported_cash")
    if debt_cash is not None and debt_cash>3:flags.append("debt_over_3x_cash")
    if fcf_now is not None and fcf_now<0:flags.append("negative_fcf")
    if cash is not None and cash>0 and (debt is None or debt<=0):flags.append("cash_no_debt")
    if r.get("score_s1") is None:flags.append("unranked_s1")
    return {"symbol":r["symbol"],"score_s1":r.get("score_s1"),"revenue":revenue,
            "cash":cash,"debt":debt,"fcf":fcf_now,"debt_to_cash":debt_cash,
            "flags":flags,"raw":r}
def main():
    with open(ROOT/"config/symbols.csv",encoding="utf-8-sig") as f:
        candidates=[x["symbol"]+".V" for x in csv.DictReader(f)
                    if x.get("market")=="XTSX" and x.get("enabled","true").lower()=="true"]
    rng=random.Random(20261008)
    candidates=sorted(set(candidates));rng.shuffle(candidates)
    # Sample 45 TSXV names with reproducible random seed, then audit all 45.
    sample=candidates[:45]
    rows=[]
    for i,sym in enumerate(sample,1):
        try:r=run(sym,"junior")
        except Exception as e:r={"symbol":sym,"sector":"junior","score_s1":None,"error":str(e)[:200]}
        rows.append(classify(r))
        print(f"AUDIT {i}/{len(sample)} {sym}: score={r.get('score_s1')} flags={rows[-1]['flags']}",flush=True)
        time.sleep(1.1)
    # Same S1 formula, no cherry-picking and no newly required Yahoo fields.
    high=[r for r in rows if r["score_s1"] is not None and r["score_s1"]>=70]
    contradictions=[r for r in high if ("negative_fcf" in r["flags"] and
                    ("debt_over_3x_cash" in r["flags"] or "debt_without_reported_cash" in r["flags"]))]
    low=[r for r in rows if r["score_s1"] is not None and r["score_s1"]<40]
    safe_low=[r for r in low if "cash_no_debt" in r["flags"]]
    missing=sum(r["score_s1"] is None for r in rows)
    report={"test":"S1-junior-audit","date":datetime.now(timezone.utc).isoformat(),
            "universe":"45 reproducibly sampled enabled TSXV symbols from config/symbols.csv",
            "seed":20261008,"total":len(rows),"ranked":len(rows)-missing,
            "unranked":missing,"high_score_with_debt_and_negative_fcf":len(contradictions),
            "low_score_with_cash_and_no_debt":len(safe_low),
            "rows":rows}
    (OUT/"s1_junior_audit_results.json").write_text(json.dumps(report,indent=2,ensure_ascii=False))
    lines=["# Audit indépendant S1 — juniors TSXV","",
           f"Échantillon reproductible : {len(rows)} juniors TSXV du registre Stockindicator, sans sélection selon leur score.",
           f"Titres avec score S1 : {len(rows)-missing}. Sans score : {missing}.",
           f"Score >=70, dette >3x trésorerie (ou trésorerie nulle) et FCF négatif : {len(contradictions)}.",
           f"Score <40 malgré trésorerie positive et dette nulle : {len(safe_low)}.",
           "",
           "Attention : une donnée absente ne prouve pas une dette nulle ni l'absence de revenus.",
           "Le champ 'junior' réutilise les seuils industriels S1. La méthodologie est un audit, pas une nouvelle calibration.",
           "",
           "| Titre | S1 | Revenus | Trésorerie | Dette | FCF | Signaux |",
           "|---|---:|---:|---:|---:|---:|---|"]
    def fmt(x):return "n.d." if x is None else f"{x:,.0f}"
    for r in sorted(rows,key=lambda x:(x["score_s1"] is None,-(x["score_s1"] or 0))):
        lines.append(f"| {r['symbol']} | {r['score_s1'] if r['score_s1'] is not None else 'n.d.'} | {fmt(r['revenue'])} | {fmt(r['cash'])} | {fmt(r['debt'])} | {fmt(r['fcf'])} | {', '.join(r['flags'])} |")
    lines.extend(["","## Cas prioritaires à examiner","",
                  "### Bons scores malgré endettement et FCF négatif"])
    lines.extend(f"- {r['symbol']}: S1 {r['score_s1']}" for r in contradictions)
    lines.append("### Faibles scores malgré trésorerie et dette nulle")
    lines.extend(f"- {r['symbol']}: S1 {r['score_s1']}" for r in safe_low)
    lines.extend(["","## Interprétation","",
        "L'audit teste le rôle du filtre Santé : favoriser les bilans solides et pénaliser les entreprises endettées sans capacité de financement.",
        "Il ne teste ni le potentiel, ni le timing, ni la volatilité, ni une probabilité de faillite.",
        "Toute calibration S2 doit rester séparée du moteur officiel et réutiliser les champs Yahoo S1."])
    (OUT/"s1_junior_audit_report.md").write_text("\n".join(lines))
    print(f"AUDIT_COMPLETE {len(rows)} ranked={len(rows)-missing} contradictions={len(contradictions)}",flush=True)
if __name__=="__main__":main()
