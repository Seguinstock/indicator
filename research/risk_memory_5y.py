"""Prototype indépendant : mémoire des drawdowns hebdomadaires sur 5 ans.

Usage local uniquement: python research/risk_memory_5y.py
Aucun fichier de production n'est modifié.
"""
import json
import time
from pathlib import Path
import numpy as np
import pandas as pd
import yfinance as yf

SYMBOLS = ["SWKS", "AAPL", "MSFT", "JNJ", "KO", "NVDA", "AMD", "INTC", "BA", "TSLA", "COST", "PG"]
THRESHOLDS = (0.15, 0.25, 0.35)


def episodes(close):
    """Un épisode commence à un sommet et se termine à sa récupération.

    Une chute non récupérée reste un épisode unique, même si elle rebondit
    puis baisse de nouveau sans retrouver son sommet initial.
    """
    values = pd.to_numeric(close, errors="coerce").dropna()
    if len(values) < 2:
        return []
    peak = float(values.iloc[0])
    peak_date = str(values.index[0].date())
    trough = peak
    trough_date = peak_date
    out = []
    for date, price in values.iloc[1:].items():
        price = float(price)
        if not np.isfinite(price) or price <= 0:
            continue
        if price >= peak:
            if trough < peak:
                out.append({"peak_date": peak_date, "trough_date": trough_date,
                            "recovery_date": str(date.date()),
                            "depth_pct": round(100 * (1 - trough / peak), 2)})
            peak, trough = price, price
            peak_date = trough_date = str(date.date())
        elif price < trough:
            trough, trough_date = price, str(date.date())
    if trough < peak:
        out.append({"peak_date": peak_date, "trough_date": trough_date,
                    "recovery_date": None,
                    "depth_pct": round(100 * (1 - trough / peak), 2)})
    return out


def historical_score(events):
    """Échelle expérimentale 0-100, non calibrée et non officielle."""
    depths = [e["depth_pct"] for e in events]
    counts = {str(int(t * 100)): sum(d >= t * 100 for d in depths) for t in THRESHOLDS}
    worst = max(depths, default=0)
    # Poids provisoires à confronter à une distribution réelle.
    score = min(100, 25 + 8 * min(counts["15"], 4)
                + 9 * min(counts["25"], 3)
                + 11 * min(counts["35"], 2)
                + 0.12 * min(worst, 80))
    return {"score_experimental": round(score, 1),
            "episode_counts": counts, "worst_drawdown_pct": round(worst, 2)}


def main():
    results = {}
    for symbol in SYMBOLS:
        try:
            frame = yf.download(symbol, period="5y", interval="1wk",
                                auto_adjust=True, progress=False, threads=False,
                                timeout=20)
            if frame.empty:
                results[symbol] = {"error": "no_data"}
                continue
            close = frame["Close"]
            if isinstance(close, pd.DataFrame):
                close = close.iloc[:, 0]
            events = episodes(close)
            results[symbol] = {"weeks": len(close), **historical_score(events),
                               "episodes": events}
        except Exception as exc:
            results[symbol] = {"error": type(exc).__name__ + ": " + str(exc)}
        time.sleep(1)
    output = Path("research/risk_memory_5y_sample.json")
    output.write_text(json.dumps(results, ensure_ascii=False, indent=2) + "\n",
                      encoding="utf-8")
    print(json.dumps({k: {a: b for a, b in v.items() if a != "episodes"}
                      for k, v in results.items()}, indent=2))


if __name__ == "__main__":
    main()
