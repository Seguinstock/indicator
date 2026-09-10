# S&P 1500 robustness study

This study intentionally stops before the later stress-test phase.

Retained strategies:
- defensive
- low_macd
- confirmed_pullback

Replacement strategies:
- defensive_rebound
- early_reversal
- balanced_quality_dip

Protocol:
- 16 deterministic random 50-calendar-day windows
- Historical S&P 1500 point-in-time membership
- Same windows for all six strategies
- Equal-weight Top 30 and Top 100
- Benchmark: S&P Composite 1500 when available, otherwise S&P 500 fallback
- Result file: data/research_sp1500.json

After results are reviewed, refine variants of the two strongest strategies before any long-horizon stress test.
