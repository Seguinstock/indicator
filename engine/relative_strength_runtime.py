import csv, json, time
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd
import yfinance as yf

import scanner

ROOT = Path(__file__).resolve().parents[1]


def _clip01(x):
    return float(np.clip(x, 0, 1))


def _close_series(h):
    if h is None or h.empty:
        return pd.Series(dtype=float)
    z = h.copy()
    if isinstance(z.columns, pd.MultiIndex):
        levels = [list(z.columns.get_level_values(i)) for i in range(z.columns.nlevels)]
        if 'Close' in levels[0]:
            z.columns = z.columns.get_level_values(0)
        elif z.columns.nlevels > 1 and 'Close' in levels[1]:
            z.columns = z.columns.get_level_values(1)
    if 'Close' not in z.columns:
        return pd.Series(dtype=float)
    c = z['Close']
    if isinstance(c, pd.DataFrame):
        c = c.iloc[:, 0]
    return c.dropna().astype(float)


def _period_return(close, sessions):
    if close is None or len(close) <= sessions:
        return 0.0
    return float((close.iloc[-1] / close.iloc[-(sessions + 1)] - 1.0) * 100.0)


def market_return_20():
    for symbol in ('^SP1500', '^GSPC'):
        try:
            h = yf.download(symbol, period='4mo', interval='1d', auto_adjust=True, progress=False)
            c = _close_series(h)
            if len(c) > 21:
                return _period_return(c, 20), symbol
        except Exception:
            continue
    return 0.0, 'unavailable'


def relative_strength_score(rsi, rvol, trend, ret20, ret60, rel20, cfg):
    m = cfg.get('buy_model', {})
    rv0 = float(m.get('rvol_floor', 0.6))
    rv1 = max(float(m.get('rvol_full', 2.0)), rv0 + 0.0001)
    rt = float(m.get('rsi_target', 58))
    rr = max(float(m.get('rsi_range', 22)), 0.0001)

    quality = {
        'relative_strength_20': _clip01((float(rel20) + 5.0) / 20.0),
        'return_60': _clip01((float(ret60) + 5.0) / 30.0),
        'trend': scanner.TREND_POTENTIAL.get(float(trend), 0.5),
        'rvol': 0.0 if rvol is None or not np.isfinite(rvol) else _clip01((float(rvol) - rv0) / (rv1 - rv0)),
        'rsi': _clip01(1.0 - abs(float(rsi) - rt) / rr),
    }
    weights = {
        'relative_strength_20': max(float(m.get('relative_strength_20_weight', 40)), 0.0),
        'return_60': max(float(m.get('return_60_weight', 25)), 0.0),
        'trend': max(float(m.get('trend_weight', 20)), 0.0),
        'rvol': max(float(m.get('rvol_weight', 10)), 0.0),
        'rsi': max(float(m.get('rsi_weight', 5)), 0.0),
    }
    total = sum(weights.values())
    if total <= 0:
        return 0.0, {k: 0.0 for k in quality}
    points = {k: weights[k] * quality[k] for k in quality}
    score = 100.0 * sum(points.values()) / total
    components = {k: round(100.0 * points[k] / total, 1) for k in points}
    return float(np.clip(score, 0, 100)), components


def sell_v14_score(x, volatility_values):
    r=x['rsi']; dr=x['delta_rsi']; rv=x['rvol']; ss=x['support_score']
    macd=x.get('macd_momentum') or 0.0; trend=x['trend']
    raw = scanner.rsi_points(100-r) + scanner.delta_rsi_points(-dr)
    if rv is not None and np.isfinite(rv):
        raw += scanner.rvol_points(rv)
    if ss is not None and np.isfinite(ss):
        raw += 10-ss
    timing = float(np.clip(raw - macd/100*10, 0, 100))
    corrected = float(np.clip(timing * scanner.TREND_SELL_FACTORS.get(trend, 1), 0, 100))
    potential = scanner.percentrank(volatility_values, x['volatility_pct']) * 100 if x.get('volatility_pct') is not None else 0
    opportunity = corrected if corrected < 50 else float(np.clip(corrected*.65 + potential*.35, 0, 100))
    return opportunity, corrected, potential
def main():
    cfg = json.loads((ROOT / 'config/parameters.json').read_text(encoding='utf-8'))
    with open(ROOT / 'config/symbols.csv', encoding='utf-8-sig') as f:
        rows = [r for r in csv.DictReader(f) if r.get('enabled', 'true').lower() == 'true']
    portfolios = scanner.load_portfolios()
    market20, benchmark_symbol = market_return_20()

    results = []
    errors = []
    failed_symbols = []
    for i in range(0, len(rows), 75):
        batch = rows[i:i + 75]
        tickers = [scanner.yahoo_symbol(r['symbol'], r['market']) for r in batch]
        try:
            raw = yf.download(tickers, period='2y', interval='1d', group_by='ticker', auto_adjust=True, threads=True, progress=False)
        except Exception as e:
            errors.append(str(e)); failed_symbols.extend(r['symbol'] for r in batch); continue
        for r, ticker in zip(batch, tickers):
            try:
                h = raw[ticker] if len(tickers) > 1 else raw
                x = scanner.calc(r, h, cfg)
                if not x:
                    failed_symbols.append(r['symbol']); continue
                c = _close_series(h)
                ret20 = _period_return(c, 20)
                ret60 = _period_return(c, 60)
                rel20 = ret20 - market20
                score, components = relative_strength_score(x['rsi'], x['rvol'], x['trend'], ret20, ret60, rel20, cfg)
                x['return_20_pct'] = round(ret20, 2)
                x['return_60_pct'] = round(ret60, 2)
                x['relative_strength_20_pct'] = round(rel20, 2)
                x['potential_components'] = components
                x['potential_score'] = round(score, 1)
                x['score'] = round(score, 1)
                results.append(x)
            except Exception as e:
                errors.append(f"{r['symbol']}: {e}"); failed_symbols.append(r['symbol'])
        time.sleep(1)

    buy = sorted(results, key=lambda x: x['score'], reverse=True)
    ranked = {}
    volatility_values = [x['volatility_pct'] for x in results if x.get('volatility_pct') is not None]
    for x in results:
        sell_score, sell_timing, sell_potential = sell_v14_score(x, volatility_values)
        y = dict(x)
        y['sell_timing_v14'] = round(sell_timing, 1)
        y['potential_v14'] = round(sell_potential, 1)
        y['sell_signal'] = scanner.sell_signal(sell_timing)
        y.pop('sell_components', None)
        y['score'] = round(sell_score, 1)
        y['filters'] = {}
        y['passed'] = True
        ranked[x['symbol']] = y

    sell_by_portfolio = {}
    for pid, p in portfolios.items():
        sell = sorted([ranked[s] for s in p['held'] if s in ranked], key=lambda x: x['score'], reverse=True)
        sell_by_portfolio[pid] = sell[:cfg['visualisation']['sell_count']]

    buy_display = buy[:cfg['visualisation']['buy_count']]
    known_names = {}
    for p in portfolios.values():
        known_names.update(p.get('names', {}))
    for x in buy_display:
        x['name'] = known_names.get(x['symbol']) or scanner.yahoo_display_name(x['symbol'], x['market'])
    for pid, p in portfolios.items():
        for x in sell_by_portfolio[pid]:
            x['name'] = p.get('names', {}).get(x['symbol']) or known_names.get(x['symbol']) or scanner.yahoo_display_name(x['symbol'], x['market'])

    default_sell = sell_by_portfolio.get('michel', [])
    now = datetime.now(timezone.utc).astimezone().isoformat()
    out = {
        'updated': now,
        'scored_at': now,
        'universe': len(rows),
        'analyzed': len(results),
        'errors': len(errors),
        'failed_symbols': sorted(set(failed_symbols)),
        'buy_model': 'relative_strength_v1',
        'sell_model': 'v14',
        'benchmark_20d_symbol': benchmark_symbol,
        'benchmark_20d_return_pct': round(market20, 3),
        'parameter_snapshot': cfg,
        'buy': buy_display,
        'sell': default_sell,
        'sell_by_portfolio': sell_by_portfolio,
        'portfolios': [{'id': pid, 'name': p['name']} for pid, p in portfolios.items()],
    }
    (ROOT / 'data/results.json').write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding='utf-8')
    counts = ', '.join(f"{pid}={len(v)}" for pid, v in sell_by_portfolio.items())
    print(f"Relative Strength scan: analyzed {len(results)}/{len(rows)}; buy={len(buy)} sell[{counts}] benchmark20={market20:.2f}% ({benchmark_symbol}) errors={len(errors)}")


if __name__ == '__main__':
    main()
