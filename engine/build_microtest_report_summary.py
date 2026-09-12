import json
from collections import defaultdict
from pathlib import Path
from statistics import mean, median

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / 'data' / 'microtest_merged_a_b1_b2.json'
DST = ROOT / 'data' / 'microtest_report_summary.json'

SELECTED = {
    'breakout_20_top10': ('breakout', 20, 10),
    'momentum_20_top10': ('momentum', 20, 10),
    'relative_strength_30_top10': ('relative_strength', 30, 10),
    'momentum_pullback_75_top10': ('momentum_pullback', 75, 10),
    'low_macd_100_top100': ('low_macd', 100, 100),
    'defensive_100_top10': ('defensive', 100, 10),
}


def r3(x):
    return None if x is None else round(float(x), 3)


def summarize_group(rows):
    if not rows:
        return None
    return {
        'combinations': len(rows),
        'mean_avg_return_pct': r3(mean(r['avg_return_pct'] for r in rows)),
        'median_avg_return_pct': r3(median(r['avg_return_pct'] for r in rows)),
        'mean_avg_excess_pct': r3(mean(r['avg_excess_pct'] for r in rows)),
        'median_avg_excess_pct': r3(median(r['avg_excess_pct'] for r in rows)),
        'mean_median_excess_pct': r3(mean(r['median_excess_pct'] for r in rows)),
        'median_median_excess_pct': r3(median(r['median_excess_pct'] for r in rows)),
        'mean_beat_rate_pct': r3(mean(r['beat_period_rate_pct'] for r in rows)),
        'median_beat_rate_pct': r3(median(r['beat_period_rate_pct'] for r in rows)),
        'positive_avg_excess_combinations': sum(r['avg_excess_pct'] > 0 for r in rows),
        'beat_rate_ge_75_combinations': sum(r['beat_period_rate_pct'] >= 75 for r in rows),
        'beat_rate_ge_87_5_combinations': sum(r['beat_period_rate_pct'] >= 87.5 for r in rows),
    }


def grouped(rows, field):
    buckets = defaultdict(list)
    for r in rows:
        buckets[str(r[field])].append(r)
    return {k: summarize_group(v) for k, v in sorted(buckets.items(), key=lambda kv: kv[0])}


def family_summary(rows):
    buckets = defaultdict(list)
    for r in rows:
        buckets[r['family']].append(r)
    out = {}
    for fam, rr in buckets.items():
        best_robust = sorted(rr, key=lambda r: (r['beat_period_rate_pct'], r['positive_period_rate_pct'], r['median_excess_pct'], r['avg_excess_pct']), reverse=True)[:10]
        best_excess = sorted(rr, key=lambda r: (r['avg_excess_pct'], r['median_excess_pct']), reverse=True)[:10]
        out[fam] = {
            'overall': summarize_group(rr),
            'by_horizon': grouped(rr, 'horizon'),
            'by_top_n': grouped(rr, 'top_n'),
            'by_exit_rule': grouped(rr, 'exit_rule'),
            'best_robust': best_robust,
            'best_excess': best_excess,
        }
    return out


def selected_views(rows):
    out = {}
    for name, (fam, h, n) in SELECTED.items():
        rr = [r for r in rows if r['family'] == fam and r['horizon'] == h and r['top_n'] == n]
        out[name] = sorted(rr, key=lambda r: (r['beat_period_rate_pct'], r['median_excess_pct'], r['avg_excess_pct']), reverse=True)
    return out


def period_benchmark(rows):
    seen = {}
    for r in rows:
        for p in r.get('period_detail', []):
            seen[p['period']] = {'period': p['period'], 'source_lot': p['source_lot'], 'asof': p['asof'], 'benchmark_pct': p['benchmark_pct']}
    return [seen[k] for k in sorted(seen)]


def main():
    data = json.loads(SRC.read_text())
    general = data['all_general_combinations']
    rsi = data['all_rsi_combinations']
    report = {
        'source_generated': data['generated'],
        'method': data['method'],
        'seed': data['seed'],
        'horizons': data['horizons'],
        'top_ns': data['top_ns'],
        'exit_rules': data['exit_rules'],
        'general_periods': data['general_periods'],
        'rsi_periods': data['rsi_periods'],
        'period_index': data['period_index'],
        'period_benchmark': period_benchmark(general),
        'general_overall': summarize_group(general),
        'general_by_family': family_summary(general),
        'general_by_horizon': grouped(general, 'horizon'),
        'general_by_top_n': grouped(general, 'top_n'),
        'general_by_exit_rule': grouped(general, 'exit_rule'),
        'general_top_50_robust': sorted(general, key=lambda r: (r['beat_period_rate_pct'], r['positive_period_rate_pct'], r['median_excess_pct'], r['avg_excess_pct']), reverse=True)[:50],
        'general_top_50_excess': sorted(general, key=lambda r: (r['avg_excess_pct'], r['median_excess_pct'], r['beat_period_rate_pct']), reverse=True)[:50],
        'selected_general': selected_views(general),
        'rsi_overall': summarize_group(rsi),
        'rsi_by_family': family_summary(rsi),
        'rsi_by_horizon': grouped(rsi, 'horizon'),
        'rsi_by_top_n': grouped(rsi, 'top_n'),
        'rsi_by_exit_rule': grouped(rsi, 'exit_rule'),
        'rsi_top_50_robust': sorted(rsi, key=lambda r: (r['beat_period_rate_pct'], r['positive_period_rate_pct'], r['median_excess_pct'], r['avg_excess_pct']), reverse=True)[:50],
        'rsi_top_50_excess': sorted(rsi, key=lambda r: (r['avg_excess_pct'], r['median_excess_pct'], r['beat_period_rate_pct']), reverse=True)[:50],
    }
    DST.write_text(json.dumps(report, ensure_ascii=False, indent=2))
    print(DST)

if __name__ == '__main__':
    main()
