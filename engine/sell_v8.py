"""V8 sell proximity model for live Stockindicator holdings.

100 means an exact validated V8 exit condition is active. Values below 100
measure readiness toward the nearest V8 exit path; values above 100 measure
how far deterioration has continued after the trigger.
"""
from __future__ import annotations

import numpy as np
import pandas as pd


def _clip01(x):
    return float(np.clip(float(x), 0.0, 1.0))


def _series(h, field):
    if h is None or h.empty or field not in h.columns:
        return pd.Series(dtype=float)
    s = h[field]
    if isinstance(s, pd.DataFrame):
        s = s.iloc[:, 0]
    s = s.dropna().astype(float)
    idx = pd.to_datetime(s.index)
    if getattr(idx, 'tz', None) is not None:
        idx = idx.tz_localize(None)
    s.index = idx
    return s


def _technical(entry_price, closes):
    vals = [float(x) for x in closes if np.isfinite(x)]
    srs = pd.Series(([float(entry_price)] * 30) + vals, dtype=float)
    delta = srs.diff()
    up = delta.clip(lower=0).rolling(14).mean()
    dn = (-delta.clip(upper=0)).rolling(14).mean()
    rs = up / dn.replace(0, np.nan)
    rsi = float((100 - 100 / (1 + rs)).iloc[-1])
    e12 = srs.ewm(span=12, adjust=False).mean()
    e26 = srs.ewm(span=26, adjust=False).mean()
    mac = e12 - e26
    sig = mac.ewm(span=9, adjust=False).mean()
    hist = float((mac - sig).iloc[-1])
    down_steps = 0
    for i in range(1, min(3, len(vals))):
        if vals[-i] < vals[-i-1]: down_steps += 1
        else: break
    exact = (hist < 0 and rsi < 48) or (len(vals) >= 3 and vals[-1] < vals[-2] < vals[-3])
    rsi_p = _clip01((60.0 - rsi) / 12.0)
    macd_p = 1.0 if hist < 0 else _clip01(1.0 / (1.0 + max(hist, 0.0) * 20.0))
    branch_macd = min(rsi_p, macd_p)
    branch_down = _clip01(down_steps / 2.0)
    return exact, max(branch_macd, branch_down), rsi, hist, down_steps


def _severity(*parts):
    return float(max(0.0, sum(max(0.0, float(x)) for x in parts)))


def score(position, h, held_score, rel20, best_score):
    try:
        entry = float(position.get('average_price') or 0)
    except (TypeError, ValueError):
        entry = 0.0
    entry_date = str(position.get('entry_date') or '').strip()
    close = _series(h, 'Close'); high = _series(h, 'High')
    if entry <= 0 or not entry_date or close.empty:
        return {'score': None, 'reason': 'DONNÉES D’ENTRÉE REQUISES', 'ready': False}
    try:
        d0 = pd.Timestamp(entry_date)
        if d0.tzinfo is not None:
            d0 = d0.tz_localize(None)
    except Exception:
        return {'score': None, 'reason': 'DATE D’ENTRÉE INVALIDE', 'ready': False}
    c = close.loc[close.index >= d0]
    if c.empty:
        c = close.tail(1)
    hs = high.loc[high.index >= d0]
    cp = float(c.iloc[-1])
    peak = max(entry, float(c.max()), float(hs.max()) if not hs.empty else float(c.max()))
    sessions = int(len(c))
    ret = (cp / entry - 1.0) * 100.0
    peak_gain = (peak / entry - 1.0) * 100.0
    dd = (cp / peak - 1.0) * 100.0
    tech, tech_p, tech_rsi, tech_macd, down_steps = _technical(entry, c.tolist())

    protect_exact = cp > entry and peak_gain >= 15.0 and dd <= -6.0 and tech
    protect_ready = min(_clip01(max(peak_gain, 0.0) / 15.0), _clip01(max(-dd, 0.0) / 6.0), tech_p)
    protect_score = 100.0 * protect_ready
    if protect_exact:
        protect_score = 100.0 + _severity(((-dd) - 6.0) * 3.0, max(0.0, 48.0-tech_rsi) * 0.35, max(0, down_steps-2) * 3.0)

    hs_ok = np.isfinite(held_score); rel_ok = np.isfinite(rel20); best_ok = np.isfinite(best_score)
    time_p = _clip01(sessions / 120.0)
    weak55 = _clip01((100.0-float(held_score))/45.0) if hs_ok else 0.0
    weak40 = _clip01((100.0-float(held_score))/60.0) if hs_ok else 0.0
    rel_p = _clip01((5.0-float(rel20))/5.0) if rel_ok else 0.0
    advantage = float(best_score-held_score) if hs_ok and best_ok else -999.0
    adv_p = _clip01(advantage/15.0)
    stagnant_p = 1.0 if -5.0 <= ret <= 5.0 else _clip01(1.0-((abs(ret)-5.0)/10.0))
    opp_exact = sessions >= 120 and -5.0 <= ret <= 5.0 and hs_ok and held_score < 55.0 and rel_ok and rel20 < 0.0 and best_ok and advantage >= 15.0
    opp_score = 100.0 * min(time_p, stagnant_p, weak55, rel_p, adv_p)
    if opp_exact:
        opp_score = 100.0 + _severity(max(0.0,55.0-held_score)*0.35, max(0.0,-rel20)*0.5, max(0.0,advantage-15.0)*0.25)

    loss_p = _clip01(max(-ret,0.0)/5.0)
    best75_p = _clip01(float(best_score)/75.0) if best_ok else 0.0
    fail_exact = sessions >= 120 and ret < -5.0 and hs_ok and held_score < 40.0 and rel_ok and rel20 < 0.0 and best_ok and best_score >= 75.0
    fail_score = 100.0 * min(time_p, loss_p, weak40, rel_p, best75_p)
    if fail_exact:
        fail_score = 100.0 + _severity(max(0.0,-ret-5.0)*2.0, max(0.0,40.0-held_score)*0.4, max(0.0,-rel20)*0.5, max(0.0,best_score-75.0)*0.2)

    paths={'protective':protect_score,'opportunity120':opp_score,'thesis_failure':fail_score}
    reason=max(paths,key=paths.get); final=float(paths[reason])
    labels={'protective':'PROTECTION DU GAIN','opportunity120':'OPPORTUNITÉ 120','thesis_failure':'THÈSE ÉCHOUÉE'}
    return {
        'score': round(final,1), 'reason': labels[reason], 'ready': final >= 100.0,
        'sessions': sessions, 'entry_price': round(entry,4), 'entry_date': entry_date,
        'return_pct': round(ret,2), 'peak_gain_pct': round(peak_gain,2), 'drawdown_from_peak_pct': round(dd,2),
        'technical_deterioration': bool(tech), 'technical_rsi': round(tech_rsi,1), 'technical_macd_hist': round(tech_macd,4),
        'held_score': round(float(held_score),1) if hs_ok else None, 'relative_strength_20_pct': round(float(rel20),2) if rel_ok else None,
        'best_replacement_score': round(float(best_score),1) if best_ok else None,
        'paths': {k:round(float(v),1) for k,v in paths.items()},
    }
