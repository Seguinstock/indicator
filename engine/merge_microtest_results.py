import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
A_HISTORICAL_COMMIT = "bc7bc0edea4ecf04bb67ee409e297ad1025d227f"
GENERAL_FAMILIES = [
    "momentum",
    "momentum_pullback",
    "breakout",
    "mean_reversion",
    "lowvol_trend",
    "acceleration",
    "relative_strength",
    "relative_contrarian",
    "low_macd",
    "defensive",
]
RSI_FAMILIES = [
    "rsi14_only",
    "rsi21_only",
    "rsi14_rsi21",
    "rsi21_delta14",
    "rsi14_rsi21_delta14",
    "rsi21_low_rsi14_accel",
]


def read_json(path: Path):
    if path.exists() and path.stat().st_size:
        try:
            data = json.loads(path.read_text())
            if data.get("period_results"):
                return data
        except Exception:
            pass
    return None


def load_lot_a():
    path = DATA / "microtest_lot_a.json"
    data = read_json(path)
    if data:
        return data, "main:data/microtest_lot_a.json"
    raw = subprocess.check_output(
        ["git", "show", f"{A_HISTORICAL_COMMIT}:data/microtest_lot_a.json"],
        cwd=ROOT,
        text=True,
    )
    data = json.loads(raw)
    if not data.get("period_results"):
        raise RuntimeError("Historical Lot A has no period_results")
    return data, f"{A_HISTORICAL_COMMIT}:data/microtest_lot_a.json"


def load_required(name: str):
    path = DATA / f"microtest_lot_{name}.json"
    data = read_json(path)
    if not data:
        raise RuntimeError(f"Missing or unusable {path}")
    return data, f"main:{path.relative_to(ROOT)}"


def validate_common(lots):
    keys = ("seed", "horizons", "top_ns", "exit_rules")
    ref = lots[0]
    for lot in lots[1:]:
        for key in keys:
            if lot.get(key) != ref.get(key):
                raise RuntimeError(f"Incompatible metadata for {key}: {ref.get(key)} != {lot.get(key)}")


def global_periods(a, b1, b2):
    out = []
    idx = 1
    for lot_name, lot in (("A", a), ("B1", b1), ("B2", b2)):
        for p in lot["period_results"]:
            q = dict(p)
            q["source_lot"] = lot_name
            q["source_period"] = p.get("period")
            q["period"] = idx
            idx += 1
            out.append(q)
    return out


def aggregate_family(periods, family, horizons, top_ns, exit_rules):
    rows = []
    for h in horizons:
        for n in top_ns:
            for rule in exit_rules:
                returns = []
                medians = []
                benches = []
                avg_days = []
                best_gains = []
                givebacks = []
                post_exits = []
                positive = 0
                beats = 0
                period_rows = []
                for p in periods:
                    hrow = p["results"].get(str(h), {})
                    fams = hrow.get("families", {})
                    if family not in fams:
                        continue
                    z = fams[family].get(str(n), {}).get(rule, {})
                    r = z.get("avg_return_pct")
                    b = hrow.get("benchmark")
                    if r is None or b is None:
                        continue
                    r = float(r)
                    b = float(b)
                    returns.append(r)
                    med = z.get("median_return_pct")
                    if med is not None:
                        medians.append(float(med))
                    benches.append(b)
                    if z.get("avg_days") is not None:
                        avg_days.append(float(z["avg_days"]))
                    if z.get("avg_best_gain_pct") is not None:
                        best_gains.append(float(z["avg_best_gain_pct"]))
                    if z.get("avg_giveback_pct") is not None:
                        givebacks.append(float(z["avg_giveback_pct"]))
                    if z.get("avg_post_exit_pct") is not None:
                        post_exits.append(float(z["avg_post_exit_pct"]))
                    positive += int(r > 0)
                    beats += int(r > b)
                    period_rows.append({
                        "period": p["period"],
                        "source_lot": p["source_lot"],
                        "asof": p["asof"],
                        "return_pct": round(r, 3),
                        "benchmark_pct": round(b, 3),
                        "excess_pct": round(r - b, 3),
                    })
                if not returns:
                    continue
                ex = np.array(returns) - np.array(benches)
                count = len(returns)
                rows.append({
                    "combination": f"{family}|{h}|{n}|{rule}",
                    "family": family,
                    "horizon": h,
                    "top_n": n,
                    "exit_rule": rule,
                    "periods": count,
                    "avg_return_pct": round(float(np.mean(returns)), 3),
                    "median_period_return_pct": round(float(np.median(returns)), 3),
                    "avg_within_period_stock_median_pct": round(float(np.mean(medians)), 3) if medians else None,
                    "avg_benchmark_pct": round(float(np.mean(benches)), 3),
                    "avg_excess_pct": round(float(np.mean(ex)), 3),
                    "median_excess_pct": round(float(np.median(ex)), 3),
                    "positive_periods": positive,
                    "positive_period_rate_pct": round(100 * positive / count, 1),
                    "beat_periods": beats,
                    "beat_period_rate_pct": round(100 * beats / count, 1),
                    "avg_days": round(float(np.mean(avg_days)), 1) if avg_days else None,
                    "avg_best_gain_pct": round(float(np.mean(best_gains)), 3) if best_gains else None,
                    "avg_giveback_pct": round(float(np.mean(givebacks)), 3) if givebacks else None,
                    "avg_post_exit_pct": round(float(np.mean(post_exits)), 3) if post_exits else None,
                    "period_detail": period_rows,
                })
    return rows


def ranking_key(row):
    # Robustness first, then typical excess, then mean excess.
    return (
        row["beat_period_rate_pct"],
        row["positive_period_rate_pct"],
        row["median_excess_pct"],
        row["avg_excess_pct"],
    )


def main():
    a, src_a = load_lot_a()
    b1, src_b1 = load_required("b1")
    b2, src_b2 = load_required("b2")
    validate_common([a, b1, b2])

    periods = global_periods(a, b1, b2)
    horizons = a["horizons"]
    top_ns = a["top_ns"]
    exit_rules = a["exit_rules"]

    general = []
    for family in GENERAL_FAMILIES:
        general.extend(aggregate_family(periods, family, horizons, top_ns, exit_rules))
    general_ranked = sorted(general, key=ranking_key, reverse=True)

    b_periods = [p for p in periods if p["source_lot"] in ("B1", "B2")]
    rsi = []
    for family in RSI_FAMILIES:
        rsi.extend(aggregate_family(b_periods, family, horizons, top_ns, exit_rules))
    rsi_ranked = sorted(rsi, key=ranking_key, reverse=True)

    out = {
        "generated": datetime.now(timezone.utc).isoformat(),
        "method": "period-level merge; no averaging of lot-level aggregate averages",
        "sources": {"A": src_a, "B1": src_b1, "B2": src_b2},
        "seed": a["seed"],
        "horizons": horizons,
        "top_ns": top_ns,
        "exit_rules": exit_rules,
        "general_periods": len(periods),
        "rsi_periods": len(b_periods),
        "general_families": GENERAL_FAMILIES,
        "rsi_families": RSI_FAMILIES,
        "period_index": [
            {"period": p["period"], "source_lot": p["source_lot"], "source_period": p["source_period"], "asof": p["asof"], "tested": p.get("tested")}
            for p in periods
        ],
        "general_leaders": general_ranked[:100],
        "rsi_leaders": rsi_ranked[:100],
        "all_general_combinations": general,
        "all_rsi_combinations": rsi,
    }
    dest = DATA / "microtest_merged_a_b1_b2.json"
    dest.write_text(json.dumps(out, ensure_ascii=False, indent=2))
    print(f"Published merged result: {dest}")
    print("\nTop 20 general:")
    for r in general_ranked[:20]:
        print(r["combination"], r["avg_return_pct"], r["median_period_return_pct"], r["avg_excess_pct"], r["beat_periods"], "/", r["periods"])
    print("\nTop 20 RSI:")
    for r in rsi_ranked[:20]:
        print(r["combination"], r["avg_return_pct"], r["median_period_return_pct"], r["avg_excess_pct"], r["beat_periods"], "/", r["periods"])


if __name__ == "__main__":
    main()
