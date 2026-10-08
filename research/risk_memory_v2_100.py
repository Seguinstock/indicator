"""Recherche indépendante sur 100 titres, 5 ans de cours hebdomadaires Yahoo.

Ne touche ni aux données ni au calcul de production Stockindicator.
Les résultats sont des scores expérimentaux, pas des recommandations.
"""
import json
import math
import time
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd
import yfinance as yf

from risk_memory_5y import episodes

GROUPS = {
    "technology": "AAPL MSFT NVDA AMD INTC SWKS AVGO QCOM TXN MU AMAT LRCX KLAC ADI CRM ADBE ORCL IBM CSCO NOW",
    "consumer": "AMZN TSLA HD LOW MCD NKE SBUX COST WMT TGT PG KO PEP CL UL ULTA BKNG CMG",
    "healthcare": "JNJ UNH ABBV MRK PFE LLY ABT TMO DHR BMY GILD AMGN ISRG MDT CVS",
    "financials": "JPM BAC WFC C GS MS V MA AXP BLK SCHW SPGI CME",
    "industrial": "BA CAT DE GE HON MMM UPS FDX RTX LMT NOC UNP CSX",
    "energy_materials": "XOM CVX COP SLB EOG OXY MPC VLO FCX NEM LIN APD",
    "communications_utilities_realestate": "GOOGL META NFLX DIS CMCSA VZ T NEE DUK",
}
SYMBOLS = [(symbol, sector) for sector, names in GROUPS.items()
           for symbol in names.split()]
assert len(SYMBOLS) == 100 and len(set(s for s, _ in SYMBOLS)) == 100

def v2_metrics(close):
    close = pd.to_numeric(close, errors="coerce").dropna()
    close = close[close > 0]
    if len(close) < 156:
        raise ValueError(f"insufficient_weekly_history:{len(close)}")
    events = episodes(close)
    worst = max((float(e["depth_pct"]) for e in events), default=0.0)
    gravity = 40 * min(worst / 65, 1) ** 1.4
    asof = close.index[-1].date()
    recovery = 30 * max((
        min(max(((date.fromisoformat(e["recovery_date"]) if e.get("recovery_date")
                  else asof) - date.fromisoformat(e["peak_date"])).days / 7, 0) / 156, 1)
        * min(float(e["depth_pct"]) / 50, 1)
        for e in events
    ), default=0)
    frequency = 20 * min(sum(
        max((float(e["depth_pct"]) - 15) / 35, 0) for e in events
    ) / 3, 1)
    weekly = close.pct_change().dropna()
    # Écart-type des rendements hebdomadaires négatifs, annualisé.
    negative = weekly[weekly < 0]
    if len(negative) < 20:
        raise ValueError(f"insufficient_negative_weeks:{len(negative)}")
    downside_vol = float(negative.std(ddof=1) * math.sqrt(52))
    # Échelle provisoire : 0 point à 10 % et 10 points à 50 % de vol. baissière.
    volatility = 10 * float(np.clip((downside_vol - .10) / .40, 0, 1))
    counts = {str(t): sum(float(e["depth_pct"]) >= t for e in events)
              for t in (15, 25, 35, 50, 60)}
    return {
        "score_v2_full": round(gravity + recovery + frequency + volatility, 2),
        "components": {"gravity_40": round(gravity, 2),
                       "recovery_30": round(recovery, 2),
                       "frequency_20": round(frequency, 2),
                       "downside_volatility_10": round(volatility, 2)},
        "downside_volatility_annualized_pct": round(downside_vol * 100, 2),
        "worst_drawdown_pct": round(worst, 2),
        "drawdown_episode_counts": counts,
        "unrecovered": any(e["recovery_date"] is None and
                           float(e["depth_pct"]) >= 15 for e in events),
        "weeks": len(close),
        "as_of": asof.isoformat(),
    }

def main():
    out = {"method": "research_v2_100_weekly_5y",
           "weights": {"gravity": 40, "recovery": 30, "frequency": 20,
                       "downside_volatility": 10},
           "universe_size": len(SYMBOLS), "results": {}}
    target = Path("research/risk_memory_v2_100_results.json")
    for idx, (symbol, sector) in enumerate(SYMBOLS, 1):
        result = None
        for attempt in range(2):
            try:
                frame = yf.download(symbol, period="5y", interval="1wk",
                                    auto_adjust=True, progress=False,
                                    threads=False, timeout=25)
                if frame.empty:
                    raise ValueError("empty_yahoo_response")
                close = frame["Close"]
                if isinstance(close, pd.DataFrame):
                    close = close.iloc[:, 0]
                result = {"sector": sector, **v2_metrics(close)}
                break
            except Exception as exc:
                result = {"sector": sector, "error": str(exc)[:180]}
                if attempt == 0:
                    time.sleep(5)
        out["results"][symbol] = result
        # Sauvegarde progressive pour conserver les données en cas d'interruption.
        target.write_text(json.dumps(out, indent=2, ensure_ascii=False) + "\n",
                          encoding="utf-8")
        print(f"{idx}/100 {symbol}: " +
              (str(result.get("score_v2_full")) if "score_v2_full" in result
               else result["error"]), flush=True)
        time.sleep(2)

if __name__ == "__main__":
    main()
