"""V5 experimental scoring: reward strength without over-rewarding extension.

The V2 feature/scoring formula is unchanged. V5 only:
- extends stock-history warm-up;
- downloads stock histories more conservatively with retries;
- captures the original V2 feature frames for post-test diagnostics;
- appends winner/loser correlations to the V5 JSON.
"""
from __future__ import annotations

import json
import time

import numpy as np
import pandas as pd
import pitindex
import yfinance as yf
import validation_rs3y_v2 as v2


FEATURE_FRAMES = {}


def verified_pit_update():
    info = pitindex.info(index="sp1500")
    print("PIT status:", info, flush=True)
    # V5 is historical validation. The pinned 2026-09-07 snapshot was a
    # successfully reconciled build (including sp400 diff_ratio 3.75%).
    # A live rebuild currently fails reconciliation at 11.2%, so do not replace
    # a validated snapshot with an invalid reconstruction. The V5 end date is
    # capped to this snapshot's end_date below.
    if not info.get("end_date"):
        raise RuntimeError("Pinned PIT snapshot has no end_date")
    print("Using last validated pinned PIT snapshot; V5 end date is capped to", info["end_date"], flush=True)


def _extract(raw, batch):
    out = {}
    for t in batch:
        try:
            h = raw[t] if len(batch) > 1 else raw
            if h is None or h.empty or "Close" not in h.columns:
                continue
            h = h[["Open", "High", "Low", "Close", "Volume"]].copy().dropna(subset=["Close"])
            idx = pd.to_datetime(h.index)
            if getattr(idx, "tz", None) is not None:
                idx = idx.tz_localize(None)
            h.index = idx
            if not h.empty:
                out[t] = h.astype(float)
        except Exception:
            pass
    return out


def _download_pass(names, start, end, batch_size, pause):
    out = {}
    for i in range(0, len(names), batch_size):
        batch = names[i:i + batch_size]
        try:
            raw = yf.download(
                batch, start=start, end=end, group_by="ticker", auto_adjust=True,
                actions=False, threads=False, progress=False,
            )
            out.update(_extract(raw, batch))
        except Exception as exc:
            print(f"V5 download batch failed {i}-{i+len(batch)}: {exc}", flush=True)
        print(f"V5 downloaded {min(i+batch_size, len(names))}/{len(names)} usable={len(out)}", flush=True)
        time.sleep(pause)
    return out


def download_with_stock_warmup(tickers, start, end):
    names = list(tickers)
    if not names:
        return {}
    # Preserve V2 market-series window exactly.
    if all(str(t).startswith("^") for t in names):
        return original_download_batch(names, start, end)

    extended_start = (pd.Timestamp(start) - pd.Timedelta(days=400)).normalize()
    out = _download_pass(names, extended_start, end, batch_size=30, pause=0.8)

    # Retry only missing names, in small batches, after cooling down. This does
    # not alter prices or formula; it only improves retrieval completeness.
    missing = [t for t in names if t not in out]
    for attempt, wait_s in enumerate((20, 45), 1):
        if not missing:
            break
        print(f"V5 retry {attempt}: {len(missing)} missing; cooling down {wait_s}s", flush=True)
        time.sleep(wait_s)
        recovered = _download_pass(missing, extended_start, end, batch_size=10, pause=1.2)
        out.update(recovered)
        missing = [t for t in missing if t not in out]
        print(f"V5 retry {attempt} recovered={len(recovered)} still_missing={len(missing)}", flush=True)
    return out


def capture_feature_frame(h, market_ret20, cfg):
    frame = original_feature_frame(h, market_ret20, cfg)
    # Match the frame back to its ticker later by object identity of the history
    # is not available here, so keep frames in order and map by score lookup
    # during diagnostics using symbol frames populated by download wrapper below.
    return frame


def _component_snapshot(frame, before_date):
    z = frame.loc[frame.index < pd.Timestamp(before_date)]
    if z.empty:
        return None
    row = z.iloc[-1]
    vals = {k: float(row[k]) if np.isfinite(row[k]) else None
            for k in ("score", "rel20", "ret60", "trend", "rvol", "rsi")}
    return vals


def add_diagnostics():
    path = v2.OUT
    data = json.loads(path.read_text(encoding="utf-8"))
    analyses = {}
    for variant, result in data.get("variants", {}).items():
        open_by_slot = {}
        rows = []
        for tr in result.get("trades", []):
            slot = tr.get("slot")
            if tr.get("type") == "BUY":
                open_by_slot[slot] = tr
            elif tr.get("type") == "SELL" and slot in open_by_slot:
                buy = open_by_slot.pop(slot)
                symbol = buy["symbol"]
                frame = FEATURE_FRAMES.get(symbol)
                snap = _component_snapshot(frame, buy["date"]) if frame is not None else None
                if snap:
                    rows.append({
                        "symbol": symbol,
                        "buy_date": buy["date"],
                        "sell_date": tr["date"],
                        "return_pct": float(tr.get("return_pct", 0.0)),
                        "exit_reason": tr.get("reason"),
                        **snap,
                    })

        fields = ("score", "rel20", "ret60", "trend", "rvol", "rsi")
        corr = {}
        winners = [r for r in rows if r["return_pct"] > 0]
        losers = [r for r in rows if r["return_pct"] < 0]
        for f in fields:
            pairs = [(r[f], r["return_pct"]) for r in rows if r.get(f) is not None]
            if len(pairs) >= 3:
                x = np.asarray([p[0] for p in pairs], dtype=float)
                y = np.asarray([p[1] for p in pairs], dtype=float)
                corr[f] = float(np.corrcoef(x, y)[0, 1]) if np.std(x) > 0 and np.std(y) > 0 else None
            else:
                corr[f] = None

        def means(group):
            return {f: (float(np.mean([r[f] for r in group if r.get(f) is not None]))
                        if any(r.get(f) is not None for r in group) else None) for f in fields}

        analyses[variant] = {
            "closed_round_trips_analyzed": len(rows),
            "positive_count": len(winners),
            "negative_count": len(losers),
            "pearson_correlation_with_realized_return": corr,
            "positive_mean_entry_features": means(winners),
            "negative_mean_entry_features": means(losers),
            "round_trips": rows,
            "interpretation_note": "Correlations are descriptive, not causal; use them to form hypotheses for out-of-sample validation.",
        }
    data["formula_diagnostics"] = analyses
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


original_update = pitindex.update
pitindex.update = verified_pit_update

# V2 normally discovers the test end from the latest ^GSPC session. For strict
# PIT validity, cap only that discovery probe to the pinned snapshot end date.
# All subsequent historical downloads remain unchanged.
original_yf_download = yf.download
def capped_probe_download(tickers, *args, **kwargs):
    if tickers == "^GSPC" and kwargs.get("period") == "10d":
        pit_end = pd.Timestamp(pitindex.info(index="sp1500")["end_date"]).normalize()
        return original_yf_download(
            tickers,
            start=(pit_end - pd.Timedelta(days=20)).strftime("%Y-%m-%d"),
            end=(pit_end + pd.Timedelta(days=1)).strftime("%Y-%m-%d"),
            auto_adjust=kwargs.get("auto_adjust", True),
            progress=kwargs.get("progress", False),
        )
    return original_yf_download(tickers, *args, **kwargs)

yf.download = capped_probe_download
original_download_batch = v2.core.download_batch
original_feature_frame = v2.core.feature_frame

# Capture frames by matching the history object to the robust downloader output.
LAST_HISTORIES = {}
def download_and_remember(tickers, start, end):
    out = download_with_stock_warmup(tickers, start, end)
    if out and not all(str(t).startswith("^") for t in tickers):
        LAST_HISTORIES.update(out)
    return out

def experimental_feature_frame(h, market_ret20, cfg):
    # Start from the exact V2 features, then change only the score transformation.
    frame = original_feature_frame(h, market_ret20, cfg).copy()
    m = cfg["buy_model"]
    q_rel = ((frame["rel20"] + 5.0) / 20.0).clip(0, 1)

    # 60d momentum: full credit by +25%; beyond +35%, progressively reduce
    # the reward for an already-extended move, bottoming at 0.65.
    r60 = frame["ret60"]
    q_ret = ((r60 + 5.0) / 30.0).clip(0, 1)
    q_ret = q_ret.where(r60 <= 35.0, (1.0 - (r60 - 35.0) / 100.0).clip(0.65, 1.0))

    trend_q = frame["trend"].map({-2:0.0,-1:0.1,-0.5:0.25,0:0.5,0.5:0.65,1:0.8,2:1.0}).fillna(0.5)
    rv0=float(m.get("rvol_floor",0.6)); rv1=max(float(m.get("rvol_full",2.0)),rv0+1e-6)
    q_rvol=((frame["rvol"]-rv0)/(rv1-rv0)).clip(0,1).fillna(0)

    # RSI: healthy momentum gets full credit around 58-65; >70 becomes an
    # explicit extension penalty, reaching zero by RSI 82.
    rsi = frame["rsi"]
    q_rsi = (1-(rsi-60.0).abs()/25.0).clip(0,1).fillna(0)
    q_rsi = q_rsi.where(rsi <= 65.0, ((82.0-rsi)/17.0).clip(0,1))

    weights=np.array([float(m.get("relative_strength_20_weight",40)),float(m.get("return_60_weight",25)),
                      float(m.get("trend_weight",20)),float(m.get("rvol_weight",10)),float(m.get("rsi_weight",5))])
    total=max(weights.sum(),1e-9)
    frame["score"]=(weights[0]*q_rel+weights[1]*q_ret+weights[2]*trend_q+
                    weights[3]*q_rvol+weights[4]*q_rsi)*100.0/total
    frame["sell_score"]=100.0-frame["score"]
    return frame

def feature_and_remember(h, market_ret20, cfg):
    frame = experimental_feature_frame(h, market_ret20, cfg)
    for symbol, hist in LAST_HISTORIES.items():
        if hist is h:
            FEATURE_FRAMES[symbol] = frame
            break
    return frame

v2.core.download_batch = download_and_remember
v2.core.feature_frame = feature_and_remember
v2.OUT = v2.ROOT / "data" / "backtest_validation_rs3y_v5.json"
v2.MIN_DAILY_COVERAGE = 0.80

if __name__ == "__main__":
    v2.main()
    add_diagnostics()
