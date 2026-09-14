"""Ultimate 3-year Stockindicator backtest.

Strategy:
- point-in-time S&P 1500 universe
- current Relative Strength scoring formula
- 10 equal initial slots ($10 each)
- surge15_6_tech protective exit, plus optional stagnation exit
- all proceeds reinvested into the highest-scoring eligible S&P 1500 name
- signals at close, execution next session open

Benchmark:
- actual S&P 100 constituent snapshot that existed on the initial purchase date
- no Stockindicator ranking or signal is used
- equal-weighted to exactly $100 total and held for the whole period
- official ^OEX buy-and-hold is also reported as a secondary sanity check
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

import continuous_rs_2y as core

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data" / "backtest_ultimate_rs3y.json"
INITIAL = 100.0
PORTFOLIO_N = 10
STALE_WINDOWS = [None, 60, 90, 120, 180]


def sp100_snapshot(asof: pd.Timestamp):
    """Read the last Wikipedia S&P 100 revision that existed by the as-of date."""
    api = "https://en.wikipedia.org/w/api.php"
    params = {
        "action": "query", "prop": "revisions", "titles": "S&P 100",
        "rvstart": f"{asof.date()}T23:59:59Z", "rvdir": "older", "rvlimit": 1,
        "rvprop": "ids|timestamp", "format": "json", "formatversion": 2,
    }
    headers = {"User-Agent": "Stockindicator-backtest/1.0 (historical index research)"}
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
            chosen = t.copy()
            chosen.columns = cols
            break
    if chosen is None:
        raise RuntimeError("Could not locate S&P 100 constituent table in historical revision")
    tickers = sorted({core.norm_ticker(x) for x in chosen["symbol"].astype(str) if str(x).strip()})
    if not (95 <= len(tickers) <= 105):
        raise RuntimeError(f"Unexpected historical S&P 100 size: {len(tickers)}")
    return tickers, {"source": "Wikipedia historical revision", "revision_id": revid, "revision_timestamp": ts, "url": url}


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


def main():
    cfg = json.loads((ROOT / "config" / "parameters.json").read_text(encoding="utf-8"))

    probe = yf.download("^GSPC", period="10d", auto_adjust=True, progress=False)
    pidx = pd.to_datetime(probe.index)
    if getattr(pidx, "tz", None) is not None:
        pidx = pidx.tz_localize(None)
    end_day = pidx.max().normalize()
    start_day = (end_day - pd.DateOffset(years=3)).normalize()
    history_start = (start_day - pd.Timedelta(days=420)).normalize()
    download_end = (end_day + pd.Timedelta(days=3)).normalize()

    monthly = list(pd.date_range(history_start, end_day, freq="MS")) + [history_start, start_day, end_day]
    union = set()
    membership_cache = {}
    for d in sorted(set(pd.Timestamp(x).normalize() for x in monthly)):
        try:
            u = set(core.constituents(d, "sp1500"))
            union.update(u)
            membership_cache[str(d.date())] = u
        except Exception as e:
            print("PIT monthly failed", d.date(), e)
    if len(union) < 500:
        raise RuntimeError(f"Insufficient S&P 1500 PIT universe: {len(union)}")

    market = core.download_batch(["^SP1500", "^GSPC", "^OEX"], history_start, download_end)
    if "^GSPC" not in market:
        raise RuntimeError("Missing ^GSPC trading calendar")
    gspc = market["^GSPC"]["Close"]
    calendar = gspc.loc[(gspc.index >= start_day) & (gspc.index <= end_day)].index
    if len(calendar) < 700:
        raise RuntimeError("Insufficient 3-year trading calendar")
    start_exec, end_exec = calendar[0], calendar[-1]
    signal_day = gspc.index[gspc.index < start_exec][-1]

    sp100_names, sp100_audit = sp100_snapshot(start_exec)
    union.update(sp100_names)

    sp1500_ok = "^SP1500" in market and len(market["^SP1500"]) and market["^SP1500"].index.max() >= calendar[-1]
    market_symbol = "^SP1500" if sp1500_ok else "^GSPC"
    mc = market[market_symbol]["Close"].reindex(gspc.index).ffill()
    market_ret20 = (mc / mc.shift(20) - 1.0) * 100.0

    histories = core.download_batch(sorted(union), history_start, download_end)
    features = {t: core.feature_frame(h, market_ret20, cfg) for t, h in histories.items()}

    daily_members = {}
    for d in calendar:
        try:
            daily_members[d] = set(core.constituents(d, "sp1500"))
        except Exception:
            keys = [pd.Timestamp(k) for k in membership_cache if pd.Timestamp(k) <= d]
            daily_members[d] = membership_cache[str(max(keys).date())] if keys else set(union)

    def score_on(t, d):
        f = features.get(t)
        if f is None:
            return np.nan
        z = f.loc[f.index <= d, "score"].dropna()
        return float(z.iloc[-1]) if len(z) else np.nan

    def px(t, d, field):
        h = histories.get(t)
        if h is None:
            return np.nan
        z = h.loc[h.index == d, field]
        return float(z.iloc[-1]) if len(z) else np.nan

    initial_universe = [t for t in daily_members[start_exec] if t in histories]
    ranked = sorted(((score_on(t, signal_day), t) for t in initial_universe), reverse=True)
    top10 = [t for s, t in ranked if np.isfinite(s) and np.isfinite(px(t, start_exec, "Open"))][:PORTFOLIO_N]
    if len(top10) != PORTFOLIO_N:
        raise RuntimeError("Could not initialize 10-position strategy")

    def simulate(stale_days):
        positions = {}
        trades = []
        for t in top10:
            op = px(t, start_exec, "Open")
            positions[t] = {"shares": 10.0 / op, "entry_price": op, "entry_date": str(start_exec.date()),
                            "capital": 10.0, "peak": op, "closes": []}
            trades.append({"type": "BUY", "date": str(start_exec.date()), "symbol": t, "price": op,
                           "value": 10.0, "reason": "initial_top10", "signal_score": score_on(t, signal_day)})

        equity = []
        pending = []
        for di, d in enumerate(calendar):
            if pending:
                prior = calendar[di - 1] if di > 0 else signal_day
                candidates = [t for t in daily_members[d] if t in histories and t not in positions]
                cand_rank = sorted(((score_on(t, prior), t) for t in candidates), reverse=True)
                for order in list(pending):
                    old, reason = order["symbol"], order["reason"]
                    if old not in positions:
                        continue
                    old_open = px(old, d, "Open")
                    if not np.isfinite(old_open):
                        continue
                    pos = positions[old]
                    floor = pos["entry_price"] if reason == "surge15_6_tech" else pos["entry_price"] * 0.93
                    if old_open < floor:
                        continue
                    positions.pop(old)
                    proceeds = pos["shares"] * old_open
                    ret = (old_open / pos["entry_price"] - 1.0) * 100.0
                    trades.append({"type": "SELL", "date": str(d.date()), "symbol": old, "price": old_open,
                                   "value": proceeds, "return_pct": ret, "reason": reason})
                    replacement = None
                    while cand_rank:
                        s, t = cand_rank.pop(0)
                        if t in positions or not np.isfinite(s):
                            continue
                        op = px(t, d, "Open")
                        if np.isfinite(op) and op > 0:
                            replacement = (t, s, op)
                            break
                    if replacement:
                        t, s, op = replacement
                        positions[t] = {"shares": proceeds / op, "entry_price": op, "entry_date": str(d.date()),
                                        "capital": proceeds, "peak": op, "closes": []}
                        trades.append({"type": "BUY", "date": str(d.date()), "symbol": t, "price": op,
                                       "value": proceeds, "reason": "replacement_best_score", "signal_score": s,
                                       "replaces": old})
                pending = []

            value = 0.0
            for t, pos in positions.items():
                cp = px(t, d, "Close")
                hp = px(t, d, "High")
                if np.isfinite(cp):
                    peak_candidate = max(cp, hp) if np.isfinite(hp) else cp
                    pos["peak"] = max(float(pos["peak"]), float(peak_candidate))
                    pos["closes"].append(float(cp))
                    value += pos["shares"] * cp
                else:
                    value += pos["capital"]
            equity.append({"date": str(d.date()), "value": value})

            if di < len(calendar) - 1:
                pending = []
                for t, pos in list(positions.items()):
                    cp = px(t, d, "Close")
                    if not np.isfinite(cp):
                        continue
                    peak = float(pos["peak"])
                    peak_gain = (peak / pos["entry_price"] - 1.0) * 100.0
                    dd = (cp / peak - 1.0) * 100.0 if peak > 0 else 0.0
                    closes = pos["closes"]
                    protect = (cp > pos["entry_price"] and peak_gain >= 15 and dd <= -6
                               and tech_deteriorating(pos["entry_price"], closes))
                    if protect:
                        pending.append({"symbol": t, "reason": "surge15_6_tech"})
                        continue
                    if stale_days is not None and len(closes) >= stale_days and peak_gain < 15:
                        ret_now = (cp / pos["entry_price"] - 1.0) * 100.0
                        if -5.0 <= ret_now <= 5.0:
                            pending.append({"symbol": t, "reason": f"stagnant_{stale_days}"})

        final_value = equity[-1]["value"]
        years = (end_exec - start_exec).days / 365.2425
        sells = [x for x in trades if x["type"] == "SELL"]
        return {
            "stagnation_sessions": stale_days,
            "final_value": final_value,
            "total_return_pct": (final_value / INITIAL - 1.0) * 100.0,
            "cagr_pct": ((final_value / INITIAL) ** (1 / years) - 1.0) * 100.0,
            "max_drawdown_pct": core.max_drawdown([x["value"] for x in equity]),
            "sales": len(sells),
            "protective_sales": sum(x["reason"] == "surge15_6_tech" for x in sells),
            "stagnant_sales": sum(str(x["reason"]).startswith("stagnant_") for x in sells),
            "win_rate_pct": (sum(x.get("return_pct", 0) > 0 for x in sells) / len(sells) * 100.0) if sells else 0.0,
            "initial_holdings": top10,
            "final_holdings": sorted(positions),
            "trades": trades,
            "equity": equity,
        }

    variants = {("baseline" if d is None else f"stale{d}"): simulate(d) for d in STALE_WINDOWS}

    # Equal-weight historical S&P 100 benchmark, normalized to exactly $100 even if the index has 101 securities.
    valid = []
    for t in sp100_names:
        op = px(t, start_exec, "Open")
        h = histories.get(t)
        if not np.isfinite(op) or h is None or h.empty:
            continue
        z = h.loc[h.index <= end_exec, "Close"].dropna()
        if len(z):
            valid.append((t, op, float(z.iloc[-1]), str(z.index[-1].date())))
    if len(valid) < 95:
        raise RuntimeError(f"S&P 100 benchmark integrity failure: only {len(valid)} usable constituents")
    dollars_each = INITIAL / len(valid)
    bench_holdings = []
    bench_final = 0.0
    for t, op, fp, last_date in valid:
        value = dollars_each * fp / op
        bench_final += value
        bench_holdings.append({"symbol": t, "initial_dollars": dollars_each, "entry_price": op,
                               "final_price": fp, "last_price_date": last_date, "final_value": value,
                               "return_pct": (fp / op - 1.0) * 100.0})
    years = (end_exec - start_exec).days / 365.2425

    oex = None
    if "^OEX" in market:
        h = market["^OEX"]
        oz = h.loc[h.index == start_exec, "Open"]
        cz = h.loc[h.index <= end_exec, "Close"].dropna()
        if len(oz) and len(cz):
            op, cp = float(oz.iloc[-1]), float(cz.iloc[-1])
            fv = INITIAL * cp / op
            oex = {"final_value": fv, "total_return_pct": (fv / INITIAL - 1.0) * 100.0,
                   "cagr_pct": ((fv / INITIAL) ** (1 / years) - 1.0) * 100.0}

    out = {
        "generated": datetime.now(timezone.utc).isoformat(),
        "methodology": {
            "period_start": str(start_exec.date()), "period_end": str(end_exec.date()), "years": years,
            "strategy": "Top 10 S&P 1500 point-in-time by Stockindicator Relative Strength formula",
            "buy_formula": "40% RS20 + 25% return60 + 20% trend + 10% RVOL + 5% RSI",
            "protective_exit": "surge15_6_tech: arm at +15%, sell after 6% drawdown from intraday High/Close peak with technical deterioration; next-open execution; no intentional loss on protective sales",
            "stagnation_exit": "optional after 60/90/120/180 sessions if never armed +15% and current return remains between -5% and +5%; next-open floor -7% from entry",
            "reinvestment": "100% of sale proceeds into highest-scoring eligible PIT S&P 1500 name not already held",
            "benchmark": "actual historical S&P 100 constituent snapshot on initial purchase date; equal-weighted to exactly $100; no Stockindicator formula",
            "execution": "signals at close, trades next session open; initial ranking prior close, initial purchase first-session open",
            "costs_slippage": "none",
        },
        "data_quality": {
            "calendar_symbol": "^GSPC", "relative_strength_benchmark": market_symbol,
            "sp1500_point_in_time": True, "sp100_snapshot": sp100_audit,
            "sp100_snapshot_count": len(sp100_names), "sp100_usable_count": len(valid),
            "period_complete": years >= 2.98,
        },
        "benchmark_sp100_equal_weight": {
            "initial_value": INITIAL, "constituents": len(valid), "initial_dollars_each": dollars_each,
            "final_value": bench_final, "total_return_pct": (bench_final / INITIAL - 1.0) * 100.0,
            "cagr_pct": ((bench_final / INITIAL) ** (1 / years) - 1.0) * 100.0,
            "holdings": bench_holdings,
        },
        "benchmark_oex_official_index": oex,
        "variants": variants,
    }
    OUT.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({
        "period": [str(start_exec.date()), str(end_exec.date())],
        "benchmark_sp100_final": bench_final,
        "variants": {k: {x: round(v[x], 4) for x in ("final_value", "total_return_pct", "cagr_pct", "max_drawdown_pct")} for k, v in variants.items()},
    }, indent=2))


if __name__ == "__main__":
    main()
