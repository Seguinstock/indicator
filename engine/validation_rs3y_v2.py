"""Corrected 3-year Stockindicator validation backtest.

Compares four exit strategies on a point-in-time S&P 1500 universe:
1) baseline: surge15_6_tech
2) opportunity120: after 120 sessions, rotate a stagnant/weak holding only when a materially better candidate exists
3) thesis_failure: opportunity120 plus an explicit exit for a deeply deteriorated loser
4) adaptive_atr: thesis_failure plus a volatility-adaptive protected trailing distance

Methodology safeguards:
- refresh pitindex before building point-in-time memberships
- signal at close, execution next session open
- historical S&P 100 equal-weight benchmark, independent of Stockindicator ranking
- daily S&P 1500 market-data coverage audit; fail rather than silently accept poor coverage
- High/Close peak tracking for protective exits
- full reinvestment of sale proceeds
- no live-strategy changes
"""
from __future__ import annotations

import io
import json
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd
import requests
import yfinance as yf
import pitindex

import continuous_rs_2y as core

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data" / "backtest_validation_rs3y_v2.json"
INITIAL = 100.0
PORTFOLIO_N = 10
MIN_DAILY_COVERAGE = 0.95
MIN_SP100_COVERAGE = 0.98
VARIANTS = ["baseline", "opportunity120", "thesis_failure", "adaptive_atr"]


def sp100_snapshot(asof: pd.Timestamp):
    api = "https://en.wikipedia.org/w/api.php"
    params = {
        "action": "query", "prop": "revisions", "titles": "S&P 100",
        "rvstart": f"{asof.date()}T23:59:59Z", "rvdir": "older", "rvlimit": 1,
        "rvprop": "ids|timestamp", "format": "json", "formatversion": 2,
    }
    headers = {"User-Agent": "Stockindicator-validation/2.0 (historical index research)"}
    r = requests.get(api, params=params, headers=headers, timeout=30)
    r.raise_for_status()
    page = r.json()["query"]["pages"][0]
    rev = page["revisions"][0]
    revid = int(rev["revid"])
    ts = rev["timestamp"]
    url = f"https://en.wikipedia.org/w/index.php?title=S%26P_100&oldid={revid}"
    html = requests.get(url, headers=headers, timeout=30)
    html.raise_for_status()
    tables = pd.read_html(io.StringIO(html.text))
    chosen = None
    for t in tables:
        cols = [str(c).strip().lower() for c in t.columns]
        if "symbol" in cols and any(c in cols for c in ("name", "company")):
            chosen = t.copy(); chosen.columns = cols; break
    if chosen is None:
        raise RuntimeError("Could not locate historical S&P 100 constituent table")
    tickers = sorted({core.norm_ticker(x) for x in chosen["symbol"].astype(str) if str(x).strip()})
    if not (95 <= len(tickers) <= 105):
        raise RuntimeError(f"Unexpected historical S&P 100 size: {len(tickers)}")
    return tickers, {"source": "Wikipedia historical revision", "revision_id": revid,
                     "revision_timestamp": ts, "url": url}


def tech_deteriorating(entry: float, closes: list[float]) -> bool:
    srs = pd.Series(([entry] * 30) + closes, dtype=float)
    if len(srs) < 16:
        return False
    delta = srs.diff()
    up = delta.clip(lower=0).rolling(14).mean()
    dn = (-delta.clip(upper=0)).rolling(14).mean()
    rs = up / dn.replace(0, np.nan)
    rsi = float((100 - 100 / (1 + rs)).iloc[-1])
    e12 = srs.ewm(span=12, adjust=False).mean()
    e26 = srs.ewm(span=26, adjust=False).mean()
    mac = e12 - e26
    sig = mac.ewm(span=9, adjust=False).mean()
    mom = float((mac - sig).iloc[-1])
    return (mom < 0 and rsi < 48) or (len(closes) >= 3 and closes[-1] < closes[-2] < closes[-3])


def atr_pct(h: pd.DataFrame, d: pd.Timestamp, period: int = 14) -> float:
    z = h.loc[h.index <= d, ["High", "Low", "Close"]].tail(period + 1)
    if len(z) < period + 1:
        return np.nan
    prev = z["Close"].shift(1)
    tr = pd.concat([(z["High"] - z["Low"]), (z["High"] - prev).abs(), (z["Low"] - prev).abs()], axis=1).max(axis=1)
    a = float(tr.tail(period).mean())
    cp = float(z["Close"].iloc[-1])
    return (a / cp * 100.0) if cp > 0 else np.nan


def main():
    # Require refreshed PIT data. If upstream refresh fails, validation should fail instead of masking staleness.
    print("Refreshing pitindex...")
    pitindex.update()

    cfg = json.loads((ROOT / "config" / "parameters.json").read_text(encoding="utf-8"))
    probe = yf.download("^GSPC", period="10d", auto_adjust=True, progress=False)
    pidx = pd.to_datetime(probe.index)
    if getattr(pidx, "tz", None) is not None: pidx = pidx.tz_localize(None)
    end_day = pidx.max().normalize()
    start_day = (end_day - pd.DateOffset(years=3)).normalize()
    history_start = (start_day - pd.Timedelta(days=420)).normalize()
    download_end = (end_day + pd.Timedelta(days=3)).normalize()

    monthly = list(pd.date_range(history_start, end_day, freq="MS")) + [history_start, start_day, end_day]
    union, membership_cache = set(), {}
    for d in sorted(set(pd.Timestamp(x).normalize() for x in monthly)):
        u = set(core.constituents(d, "sp1500"))
        union.update(u); membership_cache[str(d.date())] = u
    if len(union) < 1200:
        raise RuntimeError(f"Insufficient PIT S&P 1500 union: {len(union)}")

    market = core.download_batch(["^SP1500", "^GSPC", "^OEX"], history_start, download_end)
    if "^GSPC" not in market:
        raise RuntimeError("Missing ^GSPC trading calendar")
    gspc = market["^GSPC"]["Close"]
    calendar = gspc.loc[(gspc.index >= start_day) & (gspc.index <= end_day)].index
    if len(calendar) < 700:
        raise RuntimeError("Insufficient 3-year calendar")
    start_exec, end_exec = calendar[0], calendar[-1]
    signal_day = gspc.index[gspc.index < start_exec][-1]

    sp100_names, sp100_audit = sp100_snapshot(start_exec)
    union.update(sp100_names)

    market_symbol = "^SP1500" if "^SP1500" in market and market["^SP1500"].index.max() >= end_exec else "^GSPC"
    mc = market[market_symbol]["Close"].reindex(gspc.index).ffill()
    market_ret20 = (mc / mc.shift(20) - 1.0) * 100.0

    histories = core.download_batch(sorted(union), history_start, download_end)
    features = {t: core.feature_frame(h, market_ret20, cfg) for t, h in histories.items()}

    daily_members = {}
    coverage = []
    for d in calendar:
        members = set(core.constituents(d, "sp1500"))
        daily_members[d] = members
        usable = sum(t in histories and not histories[t].loc[histories[t].index <= d].empty for t in members)
        ratio = usable / len(members) if members else 0.0
        coverage.append({"date": str(d.date()), "members": len(members), "usable": usable, "ratio": ratio})
    min_cov = min(x["ratio"] for x in coverage)
    avg_cov = float(np.mean([x["ratio"] for x in coverage]))
    if min_cov < MIN_DAILY_COVERAGE:
        worst = min(coverage, key=lambda x: x["ratio"])
        raise RuntimeError(f"S&P1500 data coverage failed: worst {worst['ratio']:.3%} on {worst['date']} < {MIN_DAILY_COVERAGE:.0%}")

    def score_on(t, d):
        f = features.get(t)
        if f is None: return np.nan
        z = f.loc[f.index <= d, "score"].dropna()
        return float(z.iloc[-1]) if len(z) else np.nan

    def rel20_on(t, d):
        f = features.get(t)
        if f is None: return np.nan
        z = f.loc[f.index <= d, "rel20"].dropna()
        return float(z.iloc[-1]) if len(z) else np.nan

    def px(t, d, field):
        h = histories.get(t)
        if h is None: return np.nan
        z = h.loc[h.index == d, field]
        return float(z.iloc[-1]) if len(z) else np.nan

    initial = [t for t in daily_members[start_exec] if t in histories]
    ranked = sorted(((score_on(t, signal_day), t) for t in initial), reverse=True)
    top10 = [t for s, t in ranked if np.isfinite(s) and np.isfinite(px(t, start_exec, "Open"))][:PORTFOLIO_N]
    if len(top10) != PORTFOLIO_N:
        raise RuntimeError("Could not initialize 10 positions")

    def best_candidate(d, prior, positions):
        candidates = [t for t in daily_members[d] if t in histories and t not in positions]
        ranked = sorted(((score_on(t, prior), t) for t in candidates), reverse=True)
        for s, t in ranked:
            op = px(t, d, "Open")
            if np.isfinite(s) and np.isfinite(op) and op > 0:
                return t, float(s), float(op)
        return None

    def simulate(variant):
        positions, trades, equity, pending = {}, [], [], []
        for t in top10:
            op = px(t, start_exec, "Open")
            positions[t] = {"shares": 10.0/op, "entry_price": op, "entry_date": str(start_exec.date()),
                            "capital": 10.0, "peak": op, "closes": [], "sessions": 0, "slot": t}
            trades.append({"type":"BUY","date":str(start_exec.date()),"symbol":t,"price":op,"value":10.0,
                           "reason":"initial_top10","signal_score":score_on(t, signal_day),"slot":t})

        for di, d in enumerate(calendar):
            if pending:
                prior = calendar[di-1] if di > 0 else signal_day
                for order in list(pending):
                    old = order["symbol"]
                    if old not in positions: continue
                    pos = positions[old]
                    old_open = px(old, d, "Open")
                    if not np.isfinite(old_open): continue
                    # Protective exits retain no-loss execution guard. Opportunity/thesis exits may realize a loss.
                    if order["reason"] == "protective" and old_open < pos["entry_price"]:
                        continue
                    rep = best_candidate(d, prior, positions)
                    if rep is None: continue
                    t, rep_score, op = rep
                    held_score = score_on(old, prior)
                    # For opportunity exits, require material score advantage again at execution-day ranking.
                    if order["reason"] == "opportunity120" and (not np.isfinite(held_score) or rep_score < held_score + 15.0):
                        continue
                    if order["reason"] == "thesis_failure" and rep_score < 75.0:
                        continue
                    positions.pop(old)
                    proceeds = pos["shares"] * old_open
                    ret = (old_open / pos["entry_price"] - 1.0) * 100.0
                    trades.append({"type":"SELL","date":str(d.date()),"symbol":old,"price":old_open,"value":proceeds,
                                   "return_pct":ret,"reason":order["reason"],"slot":pos["slot"]})
                    positions[t] = {"shares":proceeds/op,"entry_price":op,"entry_date":str(d.date()),"capital":proceeds,
                                    "peak":op,"closes":[],"sessions":0,"slot":pos["slot"]}
                    trades.append({"type":"BUY","date":str(d.date()),"symbol":t,"price":op,"value":proceeds,
                                   "reason":"replacement_best_score","signal_score":rep_score,"replaces":old,"slot":pos["slot"]})
                pending = []

            value = 0.0
            for t, pos in positions.items():
                cp, hp = px(t, d, "Close"), px(t, d, "High")
                if np.isfinite(cp):
                    pos["sessions"] += 1
                    pos["closes"].append(float(cp))
                    pos["peak"] = max(float(pos["peak"]), float(cp), float(hp) if np.isfinite(hp) else float(cp))
                    value += pos["shares"] * cp
                else:
                    value += pos["capital"]
            equity.append({"date":str(d.date()),"value":value})

            if di >= len(calendar)-1: continue
            pending = []
            # Candidate score threshold is evaluated from current close; execution next open.
            candidate_scores = sorted((score_on(t, d), t) for t in daily_members[d] if t in histories and t not in positions)
            best_score = next((float(s) for s, _ in reversed(candidate_scores) if np.isfinite(s)), np.nan)
            for t, pos in list(positions.items()):
                cp = px(t, d, "Close")
                if not np.isfinite(cp): continue
                held_score, rel = score_on(t, d), rel20_on(t, d)
                peak_gain = (pos["peak"] / pos["entry_price"] - 1.0) * 100.0
                ret_now = (cp / pos["entry_price"] - 1.0) * 100.0
                dd = (cp / pos["peak"] - 1.0) * 100.0

                trail = 6.0
                if variant == "adaptive_atr":
                    ap = atr_pct(histories[t], d)
                    if np.isfinite(ap): trail = float(np.clip(2.0 * ap, 6.0, 12.0))
                protect = (cp > pos["entry_price"] and peak_gain >= 15.0 and dd <= -trail
                           and tech_deteriorating(pos["entry_price"], pos["closes"]))
                if protect:
                    pending.append({"symbol":t,"reason":"protective"}); continue

                if variant in ("opportunity120", "thesis_failure", "adaptive_atr") and pos["sessions"] >= 120:
                    opp = (-5.0 <= ret_now <= 5.0 and np.isfinite(held_score) and held_score < 55.0
                           and np.isfinite(rel) and rel < 0.0 and np.isfinite(best_score) and best_score >= held_score + 15.0)
                    if opp:
                        pending.append({"symbol":t,"reason":"opportunity120"}); continue

                if variant in ("thesis_failure", "adaptive_atr") and pos["sessions"] >= 120:
                    fail = (ret_now < -5.0 and np.isfinite(held_score) and held_score < 40.0
                            and np.isfinite(rel) and rel < 0.0 and np.isfinite(best_score) and best_score >= 75.0)
                    if fail:
                        pending.append({"symbol":t,"reason":"thesis_failure"})

        final_value = equity[-1]["value"]
        years = (end_exec-start_exec).days/365.2425
        sells = [x for x in trades if x["type"] == "SELL"]
        # Slot contribution: final value by original $10 lineage.
        slot_values = {}
        for t, pos in positions.items():
            cp = px(t, end_exec, "Close")
            slot_values[pos["slot"]] = pos["shares"] * cp if np.isfinite(cp) else pos["capital"]
        gains = {k:v-10.0 for k,v in slot_values.items()}
        sorted_gains = sorted(gains.items(), key=lambda kv: kv[1], reverse=True)
        return {
            "variant": variant, "final_value": final_value,
            "total_return_pct": (final_value/INITIAL-1.0)*100.0,
            "cagr_pct": ((final_value/INITIAL)**(1/years)-1.0)*100.0,
            "max_drawdown_pct": core.max_drawdown([x["value"] for x in equity]),
            "sales": len(sells), "winning_sales": sum(x.get("return_pct",0)>0 for x in sells),
            "losing_sales": sum(x.get("return_pct",0)<0 for x in sells),
            "protective_sales": sum(x.get("reason")=="protective" for x in sells),
            "opportunity_sales": sum(x.get("reason")=="opportunity120" for x in sells),
            "thesis_failure_sales": sum(x.get("reason")=="thesis_failure" for x in sells),
            "initial_holdings": top10, "final_holdings": sorted(positions),
            "slot_final_values": slot_values,
            "top_slot_gains": sorted_gains[:3],
            "return_without_best_slot_pct": (((final_value - (sorted_gains[0][1] + 10.0)) / 90.0) - 1.0) * 100.0 if sorted_gains else np.nan,
            "trades": trades, "equity": equity,
        }

    variants = {v: simulate(v) for v in VARIANTS}

    # Historical equal-weight S&P 100 benchmark. Validation fails if coverage is materially incomplete.
    valid = []
    for t in sp100_names:
        op = px(t, start_exec, "Open")
        h = histories.get(t)
        if not np.isfinite(op) or h is None or h.empty: continue
        z = h.loc[h.index <= end_exec, "Close"].dropna()
        if len(z) and z.index[-1] >= end_exec:
            valid.append((t, op, float(z.iloc[-1])))
    sp100_cov = len(valid) / len(sp100_names)
    if sp100_cov < MIN_SP100_COVERAGE:
        raise RuntimeError(f"S&P100 benchmark coverage failed: {len(valid)}/{len(sp100_names)} = {sp100_cov:.2%}")
    dollars_each = INITIAL / len(valid)
    bench_holdings, bench_final = [], 0.0
    for t, op, fp in valid:
        val = dollars_each * fp / op; bench_final += val
        bench_holdings.append({"symbol":t,"initial_dollars":dollars_each,"entry_price":op,"final_price":fp,
                               "final_value":val,"return_pct":(fp/op-1.0)*100.0})
    years = (end_exec-start_exec).days/365.2425

    out = {
        "generated": datetime.now(timezone.utc).isoformat(),
        "methodology": {
            "period_start": str(start_exec.date()), "period_end": str(end_exec.date()), "years": years,
            "strategy_universe": "S&P 1500 point-in-time, refreshed pitindex",
            "buy_formula": "40% RS20 + 25% return60 + 20% trend + 10% RVOL + 5% RSI",
            "baseline": "+15% arm, 6% drawdown from High/Close peak plus technical deterioration",
            "opportunity120": "after 120 sessions: return -5%..+5%, score<55, rel20<0, replacement score >= held+15",
            "thesis_failure": "opportunity120 plus after 120 sessions: return<-5%, score<40, rel20<0, replacement score>=75",
            "adaptive_atr": "thesis_failure plus protective trail = clamp(2*ATR14%, 6%, 12%)",
            "execution": "signals at close, trades next open; full proceeds reinvested",
            "costs_slippage": "none",
            "benchmark": "historical S&P 100 constituents at initial date, equal-weight, no Stockindicator ranking",
        },
        "data_quality": {
            "pitindex_refreshed": True,
            "sp1500_min_daily_coverage": min_cov,
            "sp1500_avg_daily_coverage": avg_cov,
            "required_sp1500_min_daily_coverage": MIN_DAILY_COVERAGE,
            "sp100_snapshot": sp100_audit,
            "sp100_snapshot_count": len(sp100_names),
            "sp100_usable_count": len(valid),
            "sp100_coverage": sp100_cov,
            "required_sp100_coverage": MIN_SP100_COVERAGE,
            "coverage_daily": coverage,
        },
        "benchmark_sp100_equal_weight": {
            "initial_value": INITIAL, "final_value": bench_final,
            "total_return_pct": (bench_final/INITIAL-1.0)*100.0,
            "cagr_pct": ((bench_final/INITIAL)**(1/years)-1.0)*100.0,
            "holdings": bench_holdings,
        },
        "variants": variants,
    }
    OUT.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({
        "period":[str(start_exec.date()),str(end_exec.date())],
        "data_quality":{"min_sp1500":min_cov,"avg_sp1500":avg_cov,"sp100":sp100_cov},
        "benchmark_sp100_final":round(bench_final,4),
        "variants":{k:{m:round(v[m],4) for m in ("final_value","total_return_pct","cagr_pct","max_drawdown_pct","sales")} for k,v in variants.items()}
    }, indent=2))


if __name__ == "__main__":
    main()
