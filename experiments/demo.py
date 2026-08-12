#!/usr/bin/env python3
"""Short single-flow LEO demo: CUBIC vs LeoAware side-by-side plots."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from leo_cc.network import LeoPathConfig
from leo_cc.ccas import CubicCCA, LeoAwareCCA, BbrCCA
from leo_cc.sim import run_sim
from leo_cc.metrics import summarize_result
from leo_cc.plotting import plot_timeseries

RESULTS = ROOT / "results"


def main() -> None:
    RESULTS.mkdir(parents=True, exist_ok=True)
    cfg = LeoPathConfig(duration_s=60, handover_interval_s=18, seed=42)
    for name, cls in [("CUBIC", CubicCCA), ("BBRv3approx", BbrCCA), ("LeoAware", LeoAwareCCA)]:
        print(f"demo {name} ...")
        res = run_sim(lambda c=cls: c(), cfg=cfg, n_flows=1)
        m = summarize_result(res)[0]
        print(
            f"  goodput={m.goodput_bps/1e6:.2f} Mbps  "
            f"p95_rtt={m.p95_rtt_s*1000:.1f} ms  "
            f"loss={m.loss_rate:.4f}  handovers={len(res.handovers)}"
        )
        plot_timeseries(res, RESULTS / f"demo_{name}_timeseries.png", title=f"Demo {name}")
    print(f"Wrote demo plots under {RESULTS}")


if __name__ == "__main__":
    main()
