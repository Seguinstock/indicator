"""V3 launcher for the corrected 3-year RS validation.

V3 keeps the live application untouched.  The backtest deliberately reuses the
same indicator/scoring primitives as the live Relative Strength runtime and
records market-data coverage instead of rejecting an otherwise usable test for
a single day below the former 95% blanket threshold.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import pitindex

import scanner
import relative_strength_runtime as live_rs
import validation_rs3y_v2 as v2


def verified_pit_update():
    info = pitindex.info(index="sp1500")
    print("PIT status:", info, flush=True)
    if info.get("is_stale"):
        print("PIT dataset is stale; attempting rebuild...", flush=True)
        original_update()
        info = pitindex.info(index="sp1500")
        print("PIT status after rebuild:", info, flush=True)
        if info.get("is_stale"):
            raise RuntimeError("PIT dataset remains stale after rebuild")
    else:
        print("PIT dataset is fresh; skipping unnecessary rebuild.", flush=True)


def live_equivalent_feature_frame(h, market_ret20, cfg):
    """Historical feature frame matching what the live RS application scores.

    Important parity details:
    - each date only sees observations available on or before that date;
    - RSI/trend use the same 500-calendar-day history restriction as scanner.calc;
    - Wilder RSI, RVOL and trend come from scanner.py (the live primitives);
    - RSI is rounded to 1 decimal and RVOL to 2 decimals before scoring, exactly
      as relative_strength_runtime receives them from scanner.calc;
    - the final score is produced by relative_strength_runtime.relative_strength_score.
    """
    h = h.copy().sort_index()
    c = h["Close"].astype(float)
    v = h["Volume"].astype(float)
    ret20 = (c / c.shift(20) - 1.0) * 100.0
    ret60 = (c / c.shift(60) - 1.0) * 100.0
    rel20 = ret20 - market_ret20.reindex(c.index).ffill()

    scores = pd.Series(np.nan, index=c.index, dtype=float)
    rsis = pd.Series(np.nan, index=c.index, dtype=float)
    rvols = pd.Series(np.nan, index=c.index, dtype=float)
    trends = pd.Series(np.nan, index=c.index, dtype=float)
    rvn = int(cfg["indicators"]["rvol_period"])
    rsi_period = int(cfg["indicators"]["rsi_period"])

    for d in c.index:
        start = pd.Timestamp(d) - pd.Timedelta(days=scanner.HISTORY_DAYS)
        z = h.loc[(h.index >= start) & (h.index <= d)].dropna(subset=["Close"])
        if len(z) < 30:
            continue
        close_arr = z["Close"].astype(float).to_numpy()
        vol_arr = z["Volume"].astype(float).to_numpy()
        rsi, _ = scanner.wilder_rsi(close_arr, rsi_period)
        if not np.isfinite(rsi):
            continue
        ref = vol_arr[-(rvn + 1):-1] if len(vol_arr) > rvn else np.array([])
        rvol = float(vol_arr[-1] / np.mean(ref)) if len(ref) and np.mean(ref) > 0 else np.nan
        trend = scanner.trend_v14(close_arr)

        # scanner.calc rounds these fields before the live RS runtime consumes them.
        rsi_live = round(float(rsi), 1)
        rvol_live = round(float(rvol), 2) if np.isfinite(rvol) else None
        r20 = float(ret20.loc[d]) if np.isfinite(ret20.loc[d]) else 0.0
        r60 = float(ret60.loc[d]) if np.isfinite(ret60.loc[d]) else 0.0
        rel = float(rel20.loc[d]) if np.isfinite(rel20.loc[d]) else 0.0
        score, _ = live_rs.relative_strength_score(rsi_live, rvol_live, trend, r20, r60, rel, cfg)

        scores.loc[d] = score
        rsis.loc[d] = rsi_live
        rvols.loc[d] = np.nan if rvol_live is None else rvol_live
        trends.loc[d] = trend

    return pd.DataFrame({
        "score": scores,
        "sell_score": 100.0 - scores,
        "ret20": ret20,
        "ret60": ret60,
        "rel20": rel20,
        "rsi": rsis,
        "rvol": rvols,
        "trend": trends,
    }, index=c.index)


original_update = pitindex.update
pitindex.update = verified_pit_update

# V3 changes only the backtest.  Live scanner/runtime files and parameters remain untouched.
v2.core.feature_frame = live_equivalent_feature_frame
v2.OUT = v2.ROOT / "data" / "backtest_validation_rs3y_v3.json"

# Coverage is now an audit metric, with an emergency floor only.  Missing histories
# are never candidates because V2 already requires `t in histories` plus finite
# score/open checks for every initial purchase and replacement.
v2.MIN_DAILY_COVERAGE = 0.80

if __name__ == "__main__":
    v2.main()
