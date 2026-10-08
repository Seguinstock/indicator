"""T1: rapport experimental du timing d'achat officiel, 100 titres, courbes 1 an.

Calcule engine.scanner.calc sans modifier les formules ni les fichiers de production.
"""
import json,time,sys
from io import BytesIO
from pathlib import Path
import numpy as np
import pandas as pd
import yfinance as yf
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from reportlab.pdfgen import canvas
from reportlab.lib.utils import ImageReader

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"engine"))
from scanner import calc
from risk_memory_v2_100 import SYMBOLS

def main():
    cfg=json.loads((ROOT/"config/parameters.json").read_text(encoding="utf-8"))
    rows=[]
    for i,(symbol,sector) in enumerate(SYMBOLS,1):
        result={"symbol":symbol,"sector":sector}
        for attempt in range(2):
            try:
                # 2 ans pour amorcer les indicateurs historiques; 1 an affiché.
                h=yf.download(symbol,period="2y",interval="1d",auto_adjust=True,
                              progress=False,threads=False,timeout=30)
                if h.empty:raise ValueError("empty_yahoo_response")
                if isinstance(h.columns,pd.MultiIndex):
                    h.columns=h.columns.get_level_values(0)
                h=h.dropna(subset=["Close"])
                if len(h)<250:raise ValueError(f"insufficient_daily_history:{len(h)}")
                score=calc({"symbol":symbol,"market":"XNYS","country":"US"},h,cfg)
                if score is None:raise ValueError("timing_not_calculated")
                # Toutes les valeurs d'indicateurs proviennent de calc officiel.
                chart=h.loc[h.index>=h.index[-1]-pd.Timedelta(days=365),"Close"]
                if len(chart)<180:raise ValueError("insufficient_one_year_chart")
                result.update({"timing":score["buy_timing"],"rsi":score["rsi"],
                               "delta_rsi":score["delta_rsi"],"rvol":score["rvol"],
                               "macd":score["macd_momentum"],"trend":score["trend"],
                               "support_score":score["support_score"],
                               "as_of":str(chart.index[-1].date()),
                               "chart_dates":[str(x.date()) for x in chart.index],
                               "chart_base100":[round(float(x/chart.iloc[0]*100),3) for x in chart]})
                break
            except Exception as exc:
                result["error"]=str(exc)[:180]
                if attempt==0:time.sleep(5)
        rows.append(result)
        print(f"{i}/100 {symbol}: {result.get('timing',result.get('error'))}",flush=True)
        time.sleep(1.5)
    ok=[x for x in rows if "timing" in x]
    ok.sort(key=lambda x:(-x["timing"],x["symbol"]))
    output={"method":"T1_official_buy_timing_v14_snapshot",
            "ranking":"highest_buy_timing_first","chart_period":"last_365_days",
            "calculation_history":"2y daily, scanner restricts to 500 calendar days",
            "successful":len(ok),"total":len(rows),
            "ranked":ok,"errors":[x for x in rows if "error" in x]}
    (ROOT/"research/t1_timing_100_results.json").write_text(json.dumps(output,ensure_ascii=False,indent=2))
    if len(ok)<95:raise RuntimeError(f"Only {len(ok)} successful timing calculations")

    pdf=ROOT/"research/classement_t1_timing_100_courbes_1_an.pdf"
    W,H=595,842
    c=canvas.Canvas(str(pdf),pagesize=(W,H))
    def label(x,y,s,size=10,bold=False):
        c.setFont("Helvetica-Bold" if bold else "Helvetica",size)
        c.drawString(x,y,s)
    label(38,780,"STOCKINDICATOR - T1 / TIMING D'ACHAT",18,True)
    label(38,750,"100 actions classees du meilleur au moins bon timing actuel",12)
    label(38,687,"PRINCIPES DE COMPARAISON",13,True)
    for i,s in enumerate([
        "Score calcule a la date de l'execution, avec la formule officielle",
        "de timing d'achat dans engine/scanner.py (sans changement).",
        "Cours ajustes quotidiens, affiches sur les 365 derniers jours.",
        "Base 100 au debut de chaque courbe. Axe vertical adapte par titre.",
        "Le score mesure une opportunite de timing, PAS le rendement passe.",
        "Un score eleve n'est pas une garantie de hausse future.",
        "Les donnees 2 ans servent uniquement au calcul des indicateurs.",
        "Recherche isolee : aucune modification des resultats de production."
    ]):label(40,650-28*i,s,10)
    c.showPage()
    for i,r in enumerate(ok):
        if i%2==0:
            label(35,810,"T1 - CLASSEMENT DU TIMING D'ACHAT",13,True)
            c.line(35,800,560,800)
        top=757-(i%2)*372
        label(36,top,f"{i+1:03d}  {r['symbol']}",16,True)
        label(195,top,f"TIMING : {r['timing']:.1f} / 100",12,True)
        label(36,top-24,f"RSI {r['rsi']:.1f}    dRSI {r['delta_rsi']:.1f}    RVOL {r['rvol'] if r['rvol'] is not None else 'N/D'}    MACD {r['macd'] if r['macd'] is not None else 'N/D'}    Trend {r['trend']}",9)
        p=pd.Series(r["chart_base100"],index=pd.to_datetime(r["chart_dates"]))
        fig,ax=plt.subplots(figsize=(8,3.3),dpi=110)
        ax.plot(p.index,p.values,color="#2267A6",linewidth=1.5)
        ax.axhline(100,color="#999999",linestyle="--",linewidth=.8)
        ax.set_ylabel("Base 100",fontsize=8)
        ax.grid(alpha=.2)
        ax.tick_params(labelsize=8)
        ax.set_xlim(p.index.min(),p.index.max())
        fig.tight_layout()
        buf=BytesIO();fig.savefig(buf,format="png",dpi=110)
        plt.close(fig);buf.seek(0)
        c.drawImage(ImageReader(buf),35,top-294,width=524,height=256)
        if i%2==1 or i==len(ok)-1:
            c.line(35,37,560,37)
            label(35,23,"T1 experimental - timing officiel Stockindicator / donnees Yahoo Finance",8)
            c.showPage()
    c.save()
    print(f"PDF_READY {pdf} {pdf.stat().st_size} bytes; ranked={len(ok)}",flush=True)

if __name__=="__main__":
    main()
