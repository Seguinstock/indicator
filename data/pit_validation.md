# Point-in-time validation V2

| Date | Coverage | New final | New peak | >=50 | >=80 | >=100 | >=200 | <10 | Legacy final | Random final | Overlap | Spearman |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 2022-01-03 | 82.1% | -11.15% | 36.81% | 33.3% | 20.0% | 13.3% | 3.3% | 50.0% | -17.74% | -12.39% | 13.3% | 0.321 |
| 2022-07-01 | 84.0% | 16.84% | 56.64% | 46.7% | 10.0% | 3.3% | 3.3% | 0.0% | 17.3% | 12.95% | 20.0% | 0.436 |
| 2023-01-03 | 85.6% | -4.03% | 47.38% | 26.7% | 13.3% | 10.0% | 3.3% | 20.0% | 2.31% | 13.48% | 3.3% | 0.305 |
| 2023-07-03 | 87.1% | 13.1% | 63.05% | 33.3% | 20.0% | 16.7% | 6.7% | 30.0% | 5.08% | 9.51% | 10.0% | -0.095 |
| 2024-01-02 | 89.6% | 20.95% | 75.59% | 56.7% | 40.0% | 20.0% | 6.7% | 20.0% | 12.73% | 10.94% | 3.3% | 0.069 |
| 2024-07-01 | 90.6% | 13.58% | 86.1% | 53.3% | 33.3% | 20.0% | 3.3% | 6.7% | 4.08% | 9.71% | 3.3% | 0.186 |
| 2025-01-02 | 92.2% | 14.36% | 69.22% | 33.3% | 23.3% | 20.0% | 3.3% | 10.0% | 3.03% | 8.54% | 0.0% | -0.009 |
| 2025-07-01 | 93.7% | 43.66% | 98.6% | 36.7% | 23.3% | 23.3% | 10.0% | 3.3% | -2.85% | 32.74% | 3.3% | 0.077 |

## Protocol corrections

- Legacy comparator is now `timing_v14` / `buy_timing`, not `score` (which currently aliases the new potential score).
- Historical prices are downloaded once for the union of PIT members, retried, cached, and reused for all as-of dates.
- The production scoring formula is not modified.

## Limitations

- Point-in-time S&P 1500 reduces survivorship bias but does not eliminate it.
- Missing Yahoo histories for delisted/renamed names are explicitly counted.
- S&P 1500 is not the full US market and excludes many microcaps/speculative issuers.