"""V4 launcher: original V2 scoring with the reliable V3 launch/data method.

V4 intentionally does NOT apply V3's live-Tableau feature/scoring override.
It runs validation_rs3y_v2 with core.feature_frame exactly as V2 defined it,
while retaining V3's PIT freshness handling and practical coverage floor.
No live application files are changed.

The V2 formula is kept unchanged. V4 extends only the stock-history warm-up
used by the original V2 feature_frame. Market benchmark downloads are left on
the original V2 window so market_ret20 remains aligned to the GSPC calendar.
"""
from __future__ import annotations

import pandas as pd
import pitindex
import validation_rs3y_v2 as v2


def verified_pit_update():
    info = pitindex.info(index="sp1500")
    print("PIT status:", info, flush=True)
    if info.get("is_stale"):
        print("PIT dataset is stale; attempting rebuild...", flush=True)
        original_update()
        info = pitindex.info(index="sp1500")
        print("PIT status after rebuild:", info, flush=True)
        if info.get("is_stale"):
            raise RuntimeError("PIT dataset remains stale after rebuild")
    else:
        print("PIT dataset is fresh; skipping unnecessary rebuild.", flush=True)


def download_with_stock_warmup(tickers, start, end):
    # The first V4 fix extended every download, including ^GSPC/^SP1500.
    # That shifted market_ret20 onto dates outside the GSPC calendar used by
    # V2, and pandas alignment made the initial stock scores NaN. Keep market
    # series exactly on V2's requested window; extend only individual stocks.
    names = list(tickers)
    if names and all(str(t).startswith("^") for t in names):
        return original_download_batch(names, start, end)
    extended_start = (pd.Timestamp(start) - pd.Timedelta(days=400)).normalize()
    return original_download_batch(names, extended_start, end)


original_update = pitindex.update
pitindex.update = verified_pit_update

# Keep original V2 feature/scoring code exactly; only extend stock warm-up.
original_download_batch = v2.core.download_batch
v2.core.download_batch = download_with_stock_warmup

v2.OUT = v2.ROOT / "data" / "backtest_validation_rs3y_v4.json"
v2.MIN_DAILY_COVERAGE = 0.80

if __name__ == "__main__":
    v2.main()
