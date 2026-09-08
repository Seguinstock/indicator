import json
import math
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

import scanner

ROOT = Path(__file__).resolve().parents[1]


def num(v, default=np.nan):
    try:
        x = float(v)
        return x if math.isfinite(x) else default
    except Exception:
        return default


def refresh_buy_row(row, cfg):
    rsi = num(row.get('rsi'))
    rvol = num(row.get('rvol'))
    trend = num(row.get('trend'), 0.0)
    volatility = num(row.get('volatility_pct'))
    support_distance = num(row.get('support_distance_pct'))

    potential, components = scanner.buy_potential_score(
        rsi, rvol, trend, volatility, support_distance, cfg
    )
    row['potential_components'] = components
    row['potential_score'] = round(potential, 1)
    row['score'] = round(potential, 1)

    f = cfg['filters']
    delta_rsi = num(row.get('delta_rsi'))
    macd = num(row.get('macd_momentum'))
    support_fraction = support_distance / 100.0 if math.isfinite(support_distance) else np.nan

    checks = {
        'rsi': (not f['rsi']['enabled']) or (math.isfinite(rsi) and rsi <= f['rsi']['buy_max']),
        'reversal': (not f['reversal']['enabled']) or (math.isfinite(delta_rsi) and delta_rsi >= f['reversal']['min_delta']),
        'support': (not f['support']['enabled']) or (math.isfinite(support_fraction) and support_fraction <= f['support']['max_distance_pct'] / 100),
        'rvol': (not f['rvol']['enabled']) or (math.isfinite(rvol) and rvol >= f['rvol']['min']),
        'macd': (not f['macd']['enabled']) or (math.isfinite(macd) and macd >= f['macd']['min_momentum']),
        'trend': (not f['trend']['enabled']) or (math.isfinite(trend) and trend >= f['trend']['min']),
    }
    row['filters'] = {k: bool(v) for k, v in checks.items()}
    row['passed'] = bool(all(checks.values()))
    return row


def main():
    cfg = json.loads((ROOT / 'config/parameters.json').read_text(encoding='utf-8'))
    path = ROOT / 'data/results.json'
    data = json.loads(path.read_text(encoding='utf-8'))

    rows = data.get('buy') or []
    if not rows:
        raise SystemExit('Aucun bassin achat existant à recalculer; un scan complet est requis.')

    refreshed = [refresh_buy_row(dict(row), cfg) for row in rows]
    refreshed.sort(key=lambda x: float(x.get('score') or 0), reverse=True)
    data['buy'] = refreshed[: int(cfg['visualisation'].get('buy_count', len(refreshed)))]
    data['buy_model'] = 'potential_v1'
    data['updated'] = datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M')
    data['update_mode'] = 'fast_rescore'

    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')
    print(f"Fast rescore: {len(refreshed)} titres recalculés sans téléchargement de marché")


if __name__ == '__main__':
    main()
