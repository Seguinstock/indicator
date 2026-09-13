import json
import os
import random
import subprocess
from pathlib import Path

import pandas as pd

import microtest_explorer as base

ROOT = Path(__file__).resolve().parents[1]
STRATEGY = os.environ.get('MICROTEST_STRATEGY', 'breakout').strip().lower()
ALLOWED = {'breakout', 'momentum', 'relative_strength'}
if STRATEGY not in ALLOWED:
    raise ValueError(f'MICROTEST_STRATEGY must be one of {sorted(ALLOWED)}')

N_PERIODS = 24
SAFE_START_MIN = pd.Timestamp('2021-04-01')
SAFE_START_MAX = pd.Timestamp('2026-04-08')
REQUEST = ROOT / 'data' / 'microtest_strategy24_request.json'


def select_24_periods():
    """Pick exactly one seeded business date from each of 24 equal time bins."""
    dates = list(pd.bdate_range(SAFE_START_MIN, SAFE_START_MAX))
    if len(dates) < N_PERIODS:
        raise RuntimeError('Not enough business dates for 24 periods')
    rng = random.Random(base.SEED)
    periods = []
    total = len(dates)
    for i in range(N_PERIODS):
        lo = (i * total) // N_PERIODS
        hi = ((i + 1) * total) // N_PERIODS
        bucket = dates[lo:hi]
        if not bucket:
            raise RuntimeError(f'Empty date bucket {i + 1}')
        periods.append(rng.choice(bucket))
    periods = sorted(periods)
    if len(periods) != N_PERIODS or len(set(periods)) != N_PERIODS:
        raise RuntimeError('Period selection did not produce 24 unique dates')
    return periods


PERIODS = select_24_periods()
base.START_MIN = SAFE_START_MIN
base.START_MAX = SAFE_START_MAX
base.N_PERIODS = N_PERIODS
base.TOP_NS = [10, 30]
base.FAMILIES = [STRATEGY]
base.pick_periods = lambda: PERIODS


def main():
    print('STRATEGY', STRATEGY)
    print('PERIODS', json.dumps([str(x.date()) for x in PERIODS]))
    print('TOP_NS', base.TOP_NS)
    print('HORIZONS', base.HORIZONS)
    print('RULES', base.RULES)
    base.main()

    src = ROOT / 'data' / 'microtest_explorer.json'
    dst = ROOT / 'data' / f'microtest_{STRATEGY}_24.json'
    if not src.exists():
        raise RuntimeError('microtest_explorer.json was not produced')

    data = json.loads(src.read_text())
    data['study'] = 'strategy24'
    data['strategy'] = STRATEGY
    data['period_selection'] = '24 equal time bins; one seeded business date per bin'
    data['top_ns'] = [10, 30]
    data['periods'] = N_PERIODS
    text = json.dumps(data, ensure_ascii=False, indent=2)
    src.write_text(text)
    dst.write_text(text)

    # Existing Explorer workflow stages microtest_explorer.json itself.
    # Pre-stage the strategy-specific copy so the same commit preserves it too.
    subprocess.run(['git', 'add', str(dst.relative_to(ROOT))], cwd=ROOT, check=True)

    # Remove a one-shot request in the same result commit, preventing accidental reruns.
    if REQUEST.exists():
        try:
            request = json.loads(REQUEST.read_text())
        except Exception:
            request = {}
        if request.get('one_shot', True):
            subprocess.run(['git', 'rm', str(REQUEST.relative_to(ROOT))], cwd=ROOT, check=True)

    print(f'Published focused 24-period result: {dst.name}')


if __name__ == '__main__':
    main()
