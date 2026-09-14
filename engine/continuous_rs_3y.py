"""Corrected 3-year launcher for the continuous Relative Strength backtest.

It reuses the audited 2-year engine while correcting the stale ^SP1500 calendar issue
and extending the requested period to three years. The trading calendar always comes
from ^GSPC. ^SP1500 remains the RS benchmark only when its data reaches the same last
session; otherwise the engine uses ^GSPC for relative strength as a documented fallback.
"""
from pathlib import Path

base = Path(__file__).with_name('continuous_rs_2y.py')
src = base.read_text(encoding='utf-8')
src = src.replace("backtest_relative_strength_continuous_2y.json", "backtest_relative_strength_continuous_3y.json")
src = src.replace("start_day=(end_day-pd.DateOffset(years=2)).normalize()", "start_day=(end_day-pd.DateOffset(years=3)).normalize()")
old = "market_symbol='^SP1500' if '^SP1500' in market else '^GSPC'\n    mc=market[market_symbol]['Close']\n    market_ret20=(mc/mc.shift(20)-1.0)*100.0\n    calendar=mc.loc[(mc.index>=start_day)&(mc.index<=end_day)].index\n    if len(calendar)<450: raise RuntimeError('Insufficient trading calendar')"
new = "gspc=market['^GSPC']['Close']\n    calendar=gspc.loc[(gspc.index>=start_day)&(gspc.index<=end_day)].index\n    if len(calendar)<700: raise RuntimeError('Insufficient 3-year trading calendar')\n    sp1500_ok=('^SP1500' in market and len(market['^SP1500']) and market['^SP1500'].index.max() >= calendar[-1])\n    market_symbol='^SP1500' if sp1500_ok else '^GSPC'\n    mc=market[market_symbol]['Close'].reindex(gspc.index).ffill()\n    market_ret20=(mc/mc.shift(20)-1.0)*100.0"
if old not in src:
    raise RuntimeError('Base engine changed: market block not found')
src = src.replace(old, new)
src = src.replace("signal_day=mc.index[mc.index<start_exec][-1]", "signal_day=gspc.index[gspc.index<start_exec][-1]")
marker = "OUTPUT.write_text(json.dumps(out,ensure_ascii=False,indent=2),encoding='utf-8')"
audit = "out['data_quality']={'calendar_symbol':'^GSPC','relative_strength_benchmark':market_symbol,'requested_years':3,'actual_calendar_sessions':len(calendar),'benchmark_initialized':len(bench_positions),'benchmark_valued_at_end':len(bench_holdings),'cash_positions_at_end':sum(1 for t in positions if t.startswith('CASH:')),'period_complete':years>=2.98}\n    if len(bench_positions)!=100 or len(bench_holdings)!=100: raise RuntimeError(f'Benchmark integrity failure: initialized={len(bench_positions)}, valued={len(bench_holdings)}')\n    if years<2.98: raise RuntimeError(f'Period integrity failure: only {years:.3f} years')\n    " + marker
if marker not in src:
    raise RuntimeError('Base engine changed: output marker not found')
src = src.replace(marker, audit)
exec(compile(src, str(base), 'exec'))
