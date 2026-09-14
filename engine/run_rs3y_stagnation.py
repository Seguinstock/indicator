import hashlib, json, os, time
from pathlib import Path
import pandas as pd
import yfinance as yf

ROOT = Path(__file__).resolve().parents[1]
CACHE = ROOT / '.cache' / 'rs3y'
CACHE.mkdir(parents=True, exist_ok=True)
PROTECTED = ROOT / 'engine' / 'continuous_rs_3y_protected.py'
DAYS_LIST = [60, 90, 120, 180]
ORIG = yf.download
stats = {'hits': 0, 'network': 0, 'retries': 0}


def symbols(args, kwargs):
    x = args[0] if args else kwargs.get('tickers', [])
    if isinstance(x, str):
        return [s for s in x.replace(',', ' ').split() if s]
    return list(x or [])


def quality(df, syms):
    if df is None or df.empty:
        return 0.0
    if len(syms) <= 1:
        try:
            if isinstance(df.columns, pd.MultiIndex):
                return 1.0 if df.notna().any().any() else 0.0
            return 1.0 if 'Close' in df and df['Close'].notna().any() else 0.0
        except Exception:
            return 0.0
    if not isinstance(df.columns, pd.MultiIndex):
        return 0.0
    top = set(map(str, df.columns.get_level_values(0)))
    good = 0
    for s in syms:
        if s in top:
            try:
                if 'Close' in df[s] and df[s]['Close'].notna().any():
                    good += 1
            except Exception:
                pass
    return good / max(len(syms), 1)


def cached_download(*args, **kwargs):
    key = hashlib.sha256(repr((args, sorted(kwargs.items()))).encode()).hexdigest()
    p = CACHE / (key + '.pkl')
    if p.exists():
        stats['hits'] += 1
        return pd.read_pickle(p)
    syms = symbols(args, kwargs)
    best, bq = None, -1.0
    for n in range(5):
        if n:
            stats['retries'] += 1
            time.sleep(min(15 * n, 60))
        kw = dict(kwargs)
        if n:
            kw['threads'] = False
        try:
            stats['network'] += 1
            df = ORIG(*args, **kw)
        except Exception:
            continue
        q = quality(df, syms)
        if q > bq:
            best, bq = df, q
        need = 1.0 if len(syms) <= 1 else 0.70
        if q >= need:
            break
    if best is None or best.empty:
        raise RuntimeError('Yahoo download failed')
    need = 1.0 if len(syms) <= 1 else 0.70
    if bq < need:
        raise RuntimeError(f'Yahoo completeness too low: {bq:.1%}')
    best.to_pickle(p)
    time.sleep(1.0)
    return best


yf.download = cached_download

base_text = PROTECTED.read_text(encoding='utf-8')

for days in DAYS_LIST:
    print(f'===== surge15_6_tech + stagnation {days} sessions =====')
    text = base_text
    text = text.replace(
        "RULE = os.environ.get('SELL_RULE', 'armed10_5').strip()",
        f"RULE = 'surge15_6_tech'\nSTALE_DAYS = {days}"
    )
    text = text.replace(
        "f\"backtest_relative_strength_continuous_3y_{RULE}.json\"",
        f"f\"backtest_relative_strength_continuous_3y_{{RULE}}_stale{days}.json\""
    )
    text = text.replace(
        "                if old_open < pos['entry_price']: continue\\n                pos=positions.pop(old); proceeds=pos['shares']*old_open",
        "                stagnant_exit=(pos.get('exit_reason')=='stagnant')\\n                if old_open < pos['entry_price'] and not stagnant_exit: continue\\n                if stagnant_exit and old_open < pos['entry_price']*0.93: continue\\n                pos=positions.pop(old); proceeds=pos['shares']*old_open"
    )
    text = text.replace(
        "src = src.replace(\"'reason':'sell_score>=70'\", f\"'reason':'{RULE}'\")",
        "src = src.replace(\"'reason':'sell_score>=70'\", \"'reason':pos.get('exit_reason','surge15_6_tech')\")"
    )
    old = "                if trigger: pending.append(t)\""
    new = (
        "                ret_since_entry=(cp/pos['entry_price']-1.0)*100.0\\n"
        f"                stagnant=(len(closes)>={days} and peak_gain<15 and -5.0<=ret_since_entry<=5.0)\\n"
        "                if trigger or stagnant:\\n"
        "                    pos['exit_reason']='stagnant' if stagnant and not trigger else 'surge15_6_tech'\\n"
        "                    pending.append(t)\""
    )
    if old not in text:
        raise RuntimeError('Could not patch sell trigger for stagnation test')
    text = text.replace(old, new)
    text = text.replace(
        "f\"'sell_formula':'{RULE}; armed only after profit threshold; trailing drawdown from peak; no-loss execution guard',\"",
        f"f\"'sell_formula':'{{RULE}} + stagnation after {days} sessions if return is -5% to +5% and +15% arm was never reached; stagnant exits may realize down to -7% at next open',\""
    )
    text = text.replace(
        "'no_loss_guard':True}}",
        f"'no_loss_guard':True,'stagnation_sessions':{days},'stagnation_band_pct':5,'stagnation_open_loss_floor_pct':-7}}"
    )

    ns = {'__file__': str(PROTECTED), '__name__': '__main__'}
    exec(compile(text, str(PROTECTED), 'exec'), ns, ns)

    p = ROOT / 'data' / f'backtest_relative_strength_continuous_3y_surge15_6_tech_stale{days}.json'
    d = json.loads(p.read_text(encoding='utf-8'))
    trades = d.get('trades', [])
    stagnant_sales = sum(1 for tr in trades if tr.get('reason') == 'stagnant')
    protected_sales = sum(1 for tr in trades if tr.get('reason') == 'surge15_6_tech')
    d['stagnation_audit'] = {
        'sessions': days,
        'band_pct': [-5, 5],
        'requires_peak_gain_below_pct': 15,
        'max_next_open_loss_pct': -7,
        'stagnant_sales': stagnant_sales,
        'protected_sales': protected_sales,
        'total_sales': len(trades),
    }
    d['download_audit'] = {'shared_cache_enabled': True, **stats}
    p.write_text(json.dumps(d, ensure_ascii=False, indent=2), encoding='utf-8')

print(json.dumps({'completed_stagnation_sessions': DAYS_LIST, **stats}, indent=2))
