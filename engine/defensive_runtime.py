import math
import numpy as np
import scanner


def _clip01(x):
    return float(np.clip(x, 0, 1))


def defensive_buy_potential_score(rsi, rvol, trend, volatility_pct, support_distance_pct, cfg):
    vol = float(volatility_pct) if np.isfinite(volatility_pct) else 100.0
    q_lowvol = 1 - _clip01((vol - 15.0) / 45.0)
    q_trend = scanner.TREND_POTENTIAL.get(float(trend), 0.5)
    q_support = 0.5 if not np.isfinite(support_distance_pct) else _clip01((8.0 - float(support_distance_pct)) / 8.0)
    q_rsi = _clip01(1 - abs(float(rsi) - 40.0) / 20.0)
    q_rvol = 0.0 if not np.isfinite(rvol) else _clip01((float(rvol) - 0.6) / 1.2)

    weights = {
        'volatility': 30.0,
        'trend': 40.0,
        'rvol': 5.0,
        'rsi': 10.0,
        'support': 15.0,
    }
    quality = {
        'volatility': q_lowvol,
        'trend': q_trend,
        'rvol': q_rvol,
        'rsi': q_rsi,
        'support': q_support,
    }
    total = sum(weights.values())
    points = {k: weights[k] * quality[k] for k in quality}
    score = 100.0 * sum(points.values()) / total
    components = {k: round(100.0 * points[k] / total, 1) for k in points}
    return float(np.clip(score, 0, 100)), components


def activate():
    scanner.buy_potential_score = defensive_buy_potential_score


if __name__ == '__main__':
    activate()
    scanner.main()
