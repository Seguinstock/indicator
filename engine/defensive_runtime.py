import numpy as np
import scanner


def _clip01(x):
    return float(np.clip(x, 0, 1))


def defensive_buy_potential_score(rsi, rvol, trend, volatility_pct, support_distance_pct, cfg):
    m = cfg['buy_model']
    v0 = float(m['volatility_floor_pct'])
    v1 = max(float(m['volatility_full_pct']), v0 + 0.0001)
    rv0 = float(m['rvol_floor'])
    rv1 = max(float(m['rvol_full']), rv0 + 0.0001)
    rt = float(m['rsi_target'])
    rr = max(float(m['rsi_range']), 0.0001)
    sd = max(float(m['support_max_distance_pct']), 0.0001)

    vol = float(volatility_pct) if np.isfinite(volatility_pct) else v1
    q_lowvol = 1 - _clip01((vol - v0) / (v1 - v0))
    q_trend = scanner.TREND_POTENTIAL.get(float(trend), 0.5)
    q_support = 0.5 if not np.isfinite(support_distance_pct) else _clip01((sd - float(support_distance_pct)) / sd)
    q_rsi = _clip01(1 - abs(float(rsi) - rt) / rr)
    q_rvol = 0.0 if not np.isfinite(rvol) else _clip01((float(rvol) - rv0) / (rv1 - rv0))

    weights = {
        'volatility': max(float(m['volatility_weight']), 0.0),
        'trend': max(float(m['trend_weight']), 0.0),
        'rvol': max(float(m['rvol_weight']), 0.0),
        'rsi': max(float(m['rsi_weight']), 0.0),
        'support': max(float(m['support_weight']), 0.0),
    }
    quality = {
        'volatility': q_lowvol,
        'trend': q_trend,
        'rvol': q_rvol,
        'rsi': q_rsi,
        'support': q_support,
    }
    total = sum(weights.values())
    if total <= 0:
        return 0.0, {k: 0.0 for k in quality}
    points = {k: weights[k] * quality[k] for k in quality}
    score = 100.0 * sum(points.values()) / total
    components = {k: round(100.0 * points[k] / total, 1) for k in points}
    return float(np.clip(score, 0, 100)), components


def activate():
    scanner.buy_potential_score = defensive_buy_potential_score


if __name__ == '__main__':
    activate()
    scanner.main()
