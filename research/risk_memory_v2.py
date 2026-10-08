"""Analyse V2 hors production à partir du JSON de la première expérience.

Usage: python research/risk_memory_v2.py research/risk_memory_5y_sample.json
Aucun appel Yahoo; aucune modification du moteur V8.
La volatilité baissière (10 %) n'est PAS disponible dans ce JSON :
les trois autres composantes (90 %) sont renormalisées à 100.
"""
import datetime as dt
import json
import sys

AS_OF = dt.date(2026, 10, 8)
WEEKS_CAP = 156


def calculate(data, as_of=AS_OF):
    results = {}
    for symbol, item in data.items():
        if "error" in item:
            results[symbol] = {"error": item["error"]}
            continue
        events = item.get("episodes", [])
        worst = float(item.get("worst_drawdown_pct", 0))
        gravity = 40 * min(worst / 65, 1) ** 1.4
        recovery = max((
            min(max(((dt.date.fromisoformat(e["recovery_date"]) if e.get("recovery_date")
                      else as_of) - dt.date.fromisoformat(e["peak_date"])).days / 7, 0)
                / WEEKS_CAP, 1)
            * min(float(e["depth_pct"]) / 50, 1)
            for e in events
        ), default=0) * 30
        # Les épisodes restent distincts : une chute de 65 % ne compte qu'une fois.
        frequency = 20 * min(sum(
            max((float(e["depth_pct"]) - 15) / 35, 0)
            for e in events
        ) / 3, 1)
        results[symbol] = {
            "risk_v1": item.get("score_experimental"),
            "risk_v2_provisional": round((gravity + recovery + frequency) / 0.9, 1),
            "gravity_40": round(gravity, 2),
            "recovery_30": round(recovery, 2),
            "frequency_20": round(frequency, 2),
            "downside_volatility_10": None,
            "worst_drawdown_pct": worst,
            "volatility_data_missing": True,
        }
    return results


if __name__ == "__main__":
    source = sys.argv[1] if len(sys.argv) > 1 else "research/risk_memory_5y_sample.json"
    with open(source, encoding="utf-8") as handle:
        data = json.load(handle)
    print(json.dumps(calculate(data), ensure_ascii=False, indent=2))
