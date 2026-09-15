"""V4 launcher: original V2 scoring with the reliable V3 launch/data method.

V4 intentionally does NOT apply V3's live-Tableau feature/scoring override.
It runs validation_rs3y_v2 with core.feature_frame exactly as V2 defined it,
while retaining V3's PIT freshness handling and practical coverage floor.
No live application files are changed.
"""
from __future__ import annotations

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


original_update = pitindex.update
pitindex.update = verified_pit_update

# Keep the original V2 scoring/feature method. Only the launcher/data-quality
# mechanics that made V3 executable are carried forward.
v2.OUT = v2.ROOT / "data" / "backtest_validation_rs3y_v4.json"
v2.MIN_DAILY_COVERAGE = 0.80

if __name__ == "__main__":
    v2.main()
