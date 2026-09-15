"""V3 launcher for the corrected 3-year RS validation.

V3 deliberately does not force pitindex.update() when the pinned PIT dataset is
still fresh. The underlying V2 simulation methodology is reused unchanged;
only the PIT startup path and output filename are changed.
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
v2.OUT = v2.ROOT / "data" / "backtest_validation_rs3y_v3.json"

if __name__ == "__main__":
    v2.main()
