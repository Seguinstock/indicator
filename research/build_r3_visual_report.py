"""PDF de recherche R3: 100 courbes hebdomadaires normalisees."""
import json,time
from pathlib import Path
from io import BytesIO
import pandas as pd
import yfinance as yf
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from reportlab.pdfgen import canvas
from reportlab.lib.utils import ImageReader

base=Path("research")
data=json.loads((base/"risk_memory_r3_100_results.json").read_text())["results"]
rank=sorted(((k,v) for k,v in data.items() if "score_r3" in v),key=lambda x:x[1]["score_r3"])
assert len(rank)==100
prices={}
errors={}
for i,(symbol,_) in enumerate(rank,1):
    for attempt in range(2):
        try:
            f=yf.download(symbol,period="5y",interval="1wk",auto_adjust=True,progress=False,threads=False,timeout=25)
            if f.empty: raise ValueError("no prices")
            p=f["Close"]
            if isinstance(p,pd.DataFrame):p=p.iloc[:,0]
            p=pd.to_numeric(p,errors="coerce").dropna()
            if len(p)<156:raise ValueError("insufficient history")
            prices[symbol]=p
            break
        except Exception as exc:
            errors[symbol]=str(exc)[:150]
            if attempt==0:time.sleep(4)
    print(f"{i}/100 {symbol}: "+("OK" if symbol in prices else errors[symbol]),flush=True)
    time.sleep(1.5)
(base/"r3_chart_fetch_status.json").write_text(json.dumps({"success":len(prices),"errors":errors},indent=2))
if len(prices)<95:raise RuntimeError("Fewer than 95 valid charts")

W,H=595,842
pdf=base/"classement_r3_100_courbes_5_ans.pdf"
c=canvas.Canvas(str(pdf),pagesize=(W,H))
def txt(x,y,s,size=10,bold=False):
    c.setFont("Helvetica-Bold" if bold else "Helvetica",size)
    c.drawString(x,y,s)
txt(38,770,"STOCKINDICATOR - RISQUE HISTORIQUE R3",19,True)
txt(38,737,"100 titres classes du risque le plus faible au plus eleve",12)
txt(38,682,"METHODE DE LECTURE",13,True)
for j,s in enumerate([
    "Cours hebdomadaires ajustes sur 5 ans, normalises a 100 au depart.",
    "Meme axe temporel sur chaque graphique. Axe vertical adapte a chaque titre.",
    "Comparer la forme et les oscillations, pas la hauteur finale du cours.",
    "R3 ignore volontairement l'ampleur du rendement total.",
    "Ponderations : amplitude 25%, duree 20%, chaos 20%,",
    "anciennete et reprise 15%, repetition des crashs 20%.",
    "Les cours sont recuperes apres le test R3; les dates peuvent differer.",
    "Recherche seulement : aucune modification de la production Stockindicator."
]):txt(40,648-29*j,s,10)
c.showPage()
for i,(sym,r) in enumerate(rank):
    if i%2==0:
        txt(35,809,"R3 - CLASSEMENT VISUEL 5 ANS",13,True)
        c.line(35,800,560,800)
    top=757-(i%2)*372
    txt(36,top,f"{i+1:03d}  {sym}",16,True)
    txt(195,top,f"R3 : {r['score_r3']:.2f} / 100",12,True)
    txt(382,top,f"Crashs : {r['crashes_25pct_count']}",10)
    txt(38,top-24,f"Pire baisse : -{r['worst_drawdown_pct']:.2f}%     R2 : {r['score_r2']:.2f}",9)
    if sym in prices:
        p=prices[sym]
        fig,ax=plt.subplots(figsize=(8,3.3),dpi=110)
        ax.plot(p.index,p/p.iloc[0]*100,color="#2267A6",linewidth=1.5)
        ax.axhline(100,color="#999999",linestyle="--",linewidth=.8)
        ax.set_ylabel("Base 100",fontsize=8)
        ax.grid(alpha=.2)
        ax.tick_params(labelsize=8)
        ax.set_xlim(p.index.min(),p.index.max())
        fig.tight_layout()
        buf=BytesIO()
        fig.savefig(buf,format="png",dpi=110)
        plt.close(fig)
        buf.seek(0)
        c.drawImage(ImageReader(buf),35,top-294,width=524,height=256)
    else:txt(45,top-140,"Courbe indisponible : "+errors.get(sym,"erreur"),10)
    if i%2==1 or i==len(rank)-1:
        c.line(35,37,560,37)
        txt(35,23,"Yahoo Finance - prix ajustes hebdomadaires / R3 experimental",8)
        c.showPage()
c.save()
print(f"PDF_READY {pdf} {pdf.stat().st_size} bytes; charts={len(prices)}",flush=True)
