"""V4 launcher: original V2 scoring with the reliable V3 launch/data method.

V4 intentionally does NOT apply V3's live-Tableau feature/scoring override.
It runs validation_rs3y_v2 with core.feature_frame exactly as V2 defined it,
while retaining V3's PIT freshness handling and practical coverage floor.
No live application files are changed.

V4 also extends the downloaded pre-start history only. This gives the original
V2 indicators enough warm-up observations to form a valid ranking on the
first signal date. It does not change the V2 formula, decision date, PIT
membership, or signal-close / next-open execution rule.
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


def download_with_warmup(tickers, start, end):
    # V2 used only 420 calendar days of pre-start history. Some valid PIT
    # constituents therefore had no finite long-trend score on the first
    # signal date. Fetching an additional 400 calendar days is historical
    # warm-up only: feature_frame and all scoring logic remain original V2.
    extended_start = (pd.Timestamp(start) - pd.Timedelta(days=400)).normalize()
    return original_download_batch(tickers, extended_start, end)


original_update = pitindex.update
pitindex.update = verified_pit_update

# Keep original V2 feature/scoring code exactly; only extend historical warm-up.
original_download_batch = v2.core.download_batch
v2.core.download_batch = download_with_warmup

# Keep the original V2 scoring/feature method. Only the launcher/data-quality
# mechanics that made V3 executable are carried forward.
v2.OUT = v2.ROOT / "data" / "backtest_validation_rs3y_v4.json"
v2.MIN_DAILY_COVERAGE = 0.80

if __name__ == "__main__":
    v2.main()
