"""Analyse autonome des familles de risque; ne modifie aucun fichier du moteur."""
import csv, json
from pathlib import Path
import numpy as np
import pandas as pd
import yfinance as yf
from scipy.cluster.hierarchy import linkage, fcluster
from scipy.spatial.distance import squareform

OUT=Path("artifacts/risk_families"); OUT.mkdir(parents=True,exist_ok=True)
SRC=Path("research/risk_families_symbols.csv")
rows=list(csv.DictReader(SRC.open(encoding="utf-8")))
def ticker(row):
    s=row["symbol"].removesuffix(".TO").removesuffix(".V").removesuffix(".CN").replace(".","-")
    return s+{"XTSE":".TO","XTSX":".V","XCNQ":".CN"}.get(row["mic"],"")
end=pd.Timestamp.utcnow().tz_localize(None).normalize()+pd.Timedelta(days=1)
start=end-pd.Timedelta(days=501)
prices={}; issues=[]
for row in rows:
    key=row["symbol"]+"@"+row["mic"]; tk=ticker(row)
    try:
        d=yf.download(tk,start=start.strftime("%Y-%m-%d"),end=end.strftime("%Y-%m-%d"),auto_adjust=True,progress=False,threads=False)
        if d.empty: raise ValueError("aucun cours")
        close=d["Close"]; close=close.iloc[:,0] if isinstance(close,pd.DataFrame) else close
        close.index=pd.to_datetime(close.index).tz_localize(None).normalize()
        prices[key]=close.astype(float)
    except Exception as exc: issues.append({"symbol":key,"ticker":tk,"error":str(exc)[:250]})
fx=yf.download("CAD=X",start=start.strftime("%Y-%m-%d"),end=end.strftime("%Y-%m-%d"),auto_adjust=True,progress=False,threads=False)
if fx.empty: raise RuntimeError("Taux USD/CAD manquant : analyse CAD impossible")
rate=fx["Close"]; rate=rate.iloc[:,0] if isinstance(rate,pd.DataFrame) else rate
rate.index=pd.to_datetime(rate.index).tz_localize(None).normalize()
all_prices=pd.DataFrame(prices).sort_index().ffill(limit=3)
rate=rate.reindex(all_prices.index).ffill(limit=3)
for row in rows:
    key=row["symbol"]+"@"+row["mic"]
    if key in all_prices and row["currency"]=="USD": all_prices[key]=all_prices[key]*rate
all_prices.to_csv(OUT/"adjusted_prices_cad.csv",index_label="date")
returns=all_prices.pct_change(fill_method=None).replace([np.inf,-np.inf],np.nan)
returns.to_csv(OUT/"daily_returns_cad.csv",index_label="date")
summary={"asof":str(end.date()-pd.Timedelta(days=1)),"instruments_requested":len(rows),"downloaded":len(prices),"issues":issues,"windows":{}}
for months in (6,12,"500d"):
    window=returns.loc[returns.index>=end-(pd.Timedelta(days=500) if months=="500d" else pd.DateOffset(months=months))]
    minimum={6:75,12:150,"500d":250}[months]
    valid=window.columns[window.notna().sum()>=minimum].tolist()
    w=window[valid]
    corr=w.corr(min_periods=minimum)
    counts=w.notna().astype(int).T.dot(w.notna().astype(int))
    corr.to_csv(OUT/f"correlation_{months}.csv")
    counts.to_csv(OUT/f"pair_observations_{months}.csv")
    # Clustering conservateur: distance de correlation; corrélation manquante = 0.
    if len(valid)>=2:
        matrix=corr.fillna(0).clip(-1,1); np.fill_diagonal(matrix.values,1)
        distance=np.sqrt(np.maximum(0,2*(1-matrix.values)))
        clusters=fcluster(linkage(squareform(distance,checks=False),method="average"),t=np.sqrt(2*(1-0.45)),criterion="distance")
        pd.DataFrame({"instrument":valid,"cluster":clusters}).to_csv(OUT/f"families_{months}.csv",index=False)
    summary["windows"][str(months)]={"eligible":len(valid),"excluded":[c for c in all_prices if c not in valid],"minimum_daily_returns":minimum}
(OUT/"summary.json").write_text(json.dumps(summary,indent=2,ensure_ascii=False),encoding="utf-8")
print(json.dumps(summary,indent=2,ensure_ascii=False))
