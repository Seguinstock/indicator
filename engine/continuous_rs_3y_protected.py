"""Run the corrected 3-year continuous Relative Strength portfolio with profit-armed exits.

Rules mirror the prior microtest exit families but add an explicit no-loss execution guard:
a position is never intentionally sold below its entry price. After a sale, all proceeds
are reinvested at the next session open into the highest-scoring eligible S&P1500 name.

Select rule with SELL_RULE. Supported:
  fixed, armed10_5, armed15_8, surge10_5_tech, surge15_6_tech, surge20_8_tech
"""
import os
from pathlib import Path

RULE = os.environ.get('SELL_RULE', 'armed10_5').strip()
ALLOWED = {'fixed','armed10_5','armed15_8','surge10_5_tech','surge15_6_tech','surge20_8_tech'}
if RULE not in ALLOWED:
    raise RuntimeError(f'Unsupported SELL_RULE: {RULE}')

base = Path(__file__).with_name('continuous_rs_2y.py')
src = base.read_text(encoding='utf-8')

# Corrected three-year period and output per rule.
src = src.replace("backtest_relative_strength_continuous_2y.json", f"backtest_relative_strength_continuous_3y_{RULE}.json")
src = src.replace("start_day=(end_day-pd.DateOffset(years=2)).normalize()", "start_day=(end_day-pd.DateOffset(years=3)).normalize()")

# Always use ^GSPC for the trading calendar. Use ^SP1500 for RS only if it covers the final session.
old_market = "market_symbol='^SP1500' if '^SP1500' in market else '^GSPC'\n    mc=market[market_symbol]['Close']\n    market_ret20=(mc/mc.shift(20)-1.0)*100.0\n    calendar=mc.loc[(mc.index>=start_day)&(mc.index<=end_day)].index\n    if len(calendar)<450: raise RuntimeError('Insufficient trading calendar')"
new_market = "gspc=market['^GSPC']['Close']\n    calendar=gspc.loc[(gspc.index>=start_day)&(gspc.index<=end_day)].index\n    if len(calendar)<700: raise RuntimeError('Insufficient 3-year trading calendar')\n    sp1500_ok=('^SP1500' in market and len(market['^SP1500']) and market['^SP1500'].index.max() >= calendar[-1])\n    market_symbol='^SP1500' if sp1500_ok else '^GSPC'\n    mc=market[market_symbol]['Close'].reindex(gspc.index).ffill()\n    market_ret20=(mc/mc.shift(20)-1.0)*100.0"
if old_market not in src:
    raise RuntimeError('Base engine changed: market block not found')
src = src.replace(old_market, new_market)
src = src.replace("signal_day=mc.index[mc.index<start_exec][-1]", "signal_day=gspc.index[gspc.index<start_exec][-1]")

# Add peak/close tracking to each slot.
src = src.replace(
    "positions[t]={'shares':10.0/op,'entry_price':op,'entry_date':str(start_exec.date()),'capital':10.0}",
    "positions[t]={'shares':10.0/op,'entry_price':op,'entry_date':str(start_exec.date()),'capital':10.0,'peak':op,'closes':[]}"
)
src = src.replace(
    "positions[replacement]={'shares':proceeds/op,'entry_price':op,'entry_date':str(d.date()),'capital':proceeds}",
    "positions[replacement]={'shares':proceeds/op,'entry_price':op,'entry_date':str(d.date()),'capital':proceeds,'peak':op,'closes':[]}"
)

# Explicit no-loss execution guard: if the next open is below entry, keep the position.
src = src.replace(
    "old_open=px(old,d,'Open')\n                if not np.isfinite(old_open): continue\n                pos=positions.pop(old); proceeds=pos['shares']*old_open",
    "old_open=px(old,d,'Open')\n                if not np.isfinite(old_open): continue\n                pos=positions[old]\n                if old_open < pos['entry_price']: continue\n                pos=positions.pop(old); proceeds=pos['shares']*old_open"
)
src = src.replace("'reason':'sell_score>=70'", f"'reason':'{RULE}'")

# Track closing peaks and the close sequence since entry.
old_value = "cp=px(t,d,'Close')\n            if np.isfinite(cp): value+=pos['shares']*cp\n            else: value+=pos['capital']"
new_value = "cp=px(t,d,'Close')\n            if np.isfinite(cp):\n                pos['peak']=max(float(pos.get('peak',pos['entry_price'])),cp)\n                pos.setdefault('closes',[]).append(cp)\n                value+=pos['shares']*cp\n            else: value+=pos['capital']"
if old_value not in src:
    raise RuntimeError('Base engine changed: valuation block not found')
src = src.replace(old_value, new_value)

# Replace symmetric deterioration selling with the tested profit-armed trailing logic.
old_sell = "pending=[]\n            for t in list(positions):\n                if t.startswith('CASH:'): continue\n                s=score_on(t,d)\n                sell=100.0-s if np.isfinite(s) else np.nan\n                if np.isfinite(sell) and sell>=SELL_THRESHOLD:\n                    pending.append(t)"
new_sell = f"pending=[]\n            for t in list(positions):\n                if t.startswith('CASH:'): continue\n                pos=positions[t]\n                cp=px(t,d,'Close')\n                if not np.isfinite(cp) or cp <= pos['entry_price']: continue\n                peak=float(pos.get('peak',pos['entry_price']))\n                peak_gain=(peak/pos['entry_price']-1.0)*100.0\n                dd=(cp/peak-1.0)*100.0 if peak>0 else 0.0\n                closes=pos.get('closes',[])\n                srs=pd.Series(([pos['entry_price']]*30)+closes,dtype=float)\n                if len(srs)>=16:\n                    delta=srs.diff(); up=delta.clip(lower=0).rolling(14).mean(); dn=(-delta.clip(upper=0)).rolling(14).mean(); rs=up/dn.replace(0,np.nan); rsi=float((100-100/(1+rs)).iloc[-1])\n                    e12=srs.ewm(span=12,adjust=False).mean(); e26=srs.ewm(span=26,adjust=False).mean(); mac=e12-e26; sig=mac.ewm(span=9,adjust=False).mean(); mom=float((mac-sig).iloc[-1])\n                else:\n                    mom=0.0; rsi=50.0\n                deteriorating=(mom<0 and rsi<48) or (len(closes)>=3 and closes[-1]<closes[-2]<closes[-3])\n                trigger=False\n                if '{RULE}'=='armed10_5': trigger=(peak_gain>=10 and dd<=-5)\n                elif '{RULE}'=='armed15_8': trigger=(peak_gain>=15 and dd<=-8)\n                elif '{RULE}'=='surge10_5_tech': trigger=(peak_gain>=10 and dd<=-5 and deteriorating)\n                elif '{RULE}'=='surge15_6_tech': trigger=(peak_gain>=15 and dd<=-6 and deteriorating)\n                elif '{RULE}'=='surge20_8_tech': trigger=(peak_gain>=20 and dd<=-8 and deteriorating)\n                elif '{RULE}'=='fixed': trigger=False\n                if trigger: pending.append(t)"
if old_sell not in src:
    raise RuntimeError('Base engine changed: sell block not found')
src = src.replace(old_sell, new_sell)

# Document rule and enforce output integrity.
src = src.replace(
    "'sell_formula':'100 - current buy-quality score; sell when deterioration >= 70',",
    f"'sell_formula':'{RULE}; armed only after profit threshold; trailing drawdown from peak; no-loss execution guard',"
)
marker = "OUTPUT.write_text(json.dumps(out,ensure_ascii=False,indent=2),encoding='utf-8')"
audit = f"out['data_quality']={{'calendar_symbol':'^GSPC','relative_strength_benchmark':market_symbol,'requested_years':3,'actual_calendar_sessions':len(calendar),'benchmark_initialized':len(bench_positions),'benchmark_valued_at_end':len(bench_holdings),'cash_positions_at_end':sum(1 for t in positions if t.startswith('CASH:')),'period_complete':years>=2.98,'sell_rule':'{RULE}','no_loss_guard':True}}\n    if len(bench_positions)!=100 or len(bench_holdings)!=100: raise RuntimeError(f'Benchmark integrity failure: initialized={{len(bench_positions)}}, valued={{len(bench_holdings)}}')\n    if years<2.98: raise RuntimeError(f'Period integrity failure: only {{years:.3f}} years')\n    " + marker
if marker not in src:
    raise RuntimeError('Base engine changed: output marker not found')
src = src.replace(marker, audit)

exec(compile(src, str(base), 'exec'))
