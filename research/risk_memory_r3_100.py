"""R3: risque historique 5 ans, indépendant de tout rendement total.

Prototype de recherche uniquement; ne modifie aucune logique de production.
"""
import json
import math
import time
from pathlib import Path
import numpy as np
import pandas as pd
import yfinance as yf
from risk_memory_v2_100 import SYMBOLS, v2_metrics

def clamp(x):
    return float(np.clip(x, 0, 1))

def score_r3(close):
    p = pd.to_numeric(close, errors="coerce").dropna()
    p = p[(p > 0) & np.isfinite(p)]
    if len(p) < 156:
        raise ValueError(f"insufficient_weekly_history:{len(p)}")
    a = p.to_numpy(dtype=float)
    n = len(a)
    running_peak = np.maximum.accumulate(a)
    dd = 1 - a / running_peak
    worst = float(dd.max())
    # Amplitude: les corrections courantes sous 10% sont peu pénalisées.
    severity = 25 * clamp((worst - .10) / .55) ** 1.25

    # Durée et profondeur sous le dernier sommet (pondération quadratique).
    underwater = np.maximum(dd - .05, 0)
    area = float(np.mean(underwater ** 1.35))
    duration = 20 * clamp(area / (.20 ** 1.35))

    # Chaoticité: mouvements hebdomadaires dans les DEUX directions,
    # sans récompenser ni pénaliser le rendement total.
    lr = np.diff(np.log(a))
    noise = float(np.sqrt(np.mean((lr - np.median(lr)) ** 2)) * math.sqrt(52))
    # Pénaliser en plus les retournements fréquents de forte amplitude.
    sign = np.sign(lr)
    whipsaws = float(np.mean((sign[1:] * sign[:-1] < 0) *
                            np.minimum(np.abs(lr[1:]), np.abs(lr[:-1])))) if len(lr)>1 else 0
    chaos = 20 * (.8 * clamp((noise - .12) / .45) +
                  .2 * clamp(whipsaws / .025))

    # Crashs distincts: nouvel épisode après rebond d'au moins 20% depuis
    # le creux précédent, même sans retrouver l'ancien sommet historique.
    # Cela évite de cacher plusieurs effondrements sous un seul drawdown.
    crash_events = []
    peak = a[0]
    peak_idx = 0
    trough = a[0]
    trough_idx = 0
    active = False
    for i in range(1, n):
        price = a[i]
        if price >= peak:
            peak, peak_idx, trough, trough_idx, active = price, i, price, i, False
        elif price < trough:
            trough, trough_idx = price, i
        if not active and 1 - price / peak >= .25:
            active = True
            crash_events.append({"peak_week": peak_idx, "start_week": i,
                                 "peak_price": float(peak), "trough_week": i,
                                 "trough_price": float(price)})
        elif active:
            event = crash_events[-1]
            if price < event["trough_price"]:
                event["trough_price"] = float(price)
                event["trough_week"] = i
            # Reprise significative : une autre chute de 25% depuis un nouveau
            # sommet local pourra compter comme crash distinct.
            if price >= event["trough_price"] * 1.20:
                peak, peak_idx, trough, trough_idx, active = price, i, price, i, False
    crash_depths = [1-e["trough_price"]/e["peak_price"] for e in crash_events]
    crash_count = len(crash_events)
    repeat = 20 * clamp(sum(clamp((d-.20)/.35) for d in crash_depths) / 3)

    # Récence et qualité de la reprise: forte baisse récente plus pénalisante,
    # tandis qu'une ancienne chute suivie de stabilité perd de son poids.
    recent = []
    for e,d in zip(crash_events, crash_depths):
        weeks_ago = n - 1 - e["trough_week"]
        age_weight = math.exp(-weeks_ago / 78)  # demi-vie ~54 semaines
        since = a[e["trough_week"]:]
        recovered = bool(np.any(since >= e["peak_price"]))
        # Reprise chaotique mesurée sur les 52 dernières semaines disponibles
        tail = np.diff(np.log(since[-53:])) if len(since)>2 else np.array([])
        rebound_noise = float(np.std(tail)*math.sqrt(52)) if len(tail)>4 else 0
        unrecovered_factor = 1 if not recovered else .45
        recent.append(clamp(d/.65) * age_weight *
                      unrecovered_factor * (1 + .35*clamp((rebound_noise-.15)/.4)))
    recency = 15 * clamp(sum(recent) / 1.5)
    components = {"amplitude_25":severity,"duration_20":duration,
                  "chaos_20":chaos,"recency_recovery_15":recency,
                  "repeated_crashes_20":repeat}
    score = sum(components.values())
    return {"score_r3":round(score,2),
            "components":{k:round(v,2) for k,v in components.items()},
            "worst_drawdown_pct":round(worst*100,2),
            "crashes_25pct_count":crash_count,
            "crash_depths_pct":[round(d*100,2) for d in crash_depths],
            "annualized_weekly_noise_pct":round(noise*100,2),
            "underwater_area":round(area,5),
            "weeks":n,"as_of":str(p.index[-1].date())}

def main():
    out={"method":"R3_100_weekly_5y_experimental",
         "weights":{"amplitude":25,"duration":20,"chaos":20,
                    "recency_recovery":15,"repeated_crashes":20},
         "universe_size":len(SYMBOLS),"results":{}}
    target=Path("research/risk_memory_r3_100_results.json")
    for i,(symbol,sector) in enumerate(SYMBOLS,1):
        for attempt in range(2):
            try:
                f=yf.download(symbol,period="5y",interval="1wk",auto_adjust=True,
                              progress=False,threads=False,timeout=25)
                if f.empty: raise ValueError("empty_yahoo_response")
                close=f["Close"]
                if isinstance(close,pd.DataFrame): close=close.iloc[:,0]
                r={"sector":sector,**score_r3(close),
                   "score_r2":v2_metrics(close)["score_v2_full"]}
                break
            except Exception as exc:
                r={"sector":sector,"error":str(exc)[:180]}
                if attempt==0: time.sleep(5)
        out["results"][symbol]=r
        target.write_text(json.dumps(out,indent=2,ensure_ascii=False)+"\n",encoding="utf-8")
        print(f"{i}/100 {symbol}: {r.get('score_r3',r.get('error'))}",flush=True)
        time.sleep(2)
    good=sum("score_r3" in r for r in out["results"].values())
    print(f"COMPLETE {good}/100",flush=True)
    if good < 90: raise RuntimeError(f"Too few valid results: {good}/100")

if __name__=="__main__":
    main()
