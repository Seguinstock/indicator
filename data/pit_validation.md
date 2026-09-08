# Point-in-time validation V2

| Date | Coverage | New final | New peak | >=50 | >=80 | >=100 | >=200 | <10 | Legacy final | Random final | Overlap | Spearman |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|

## Protocol corrections

- Legacy comparator is now `timing_v14` / `buy_timing`, not `score` (which currently aliases the new potential score).
- Historical prices are downloaded once for the union of PIT members, retried, cached, and reused for all as-of dates.
- The production scoring formula is not modified.

## Limitations

- Point-in-time S&P 1500 reduces survivorship bias but does not eliminate it.
- Missing Yahoo histories for delisted/renamed names are explicitly counted.
- S&P 1500 is not the full US market and excludes many microcaps/speculative issuers.