#!/usr/bin/env python3
"""Short w1 probe: Crest vs Crest+SH vs BBR (25s, includes t=12 spike)."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from experiments.run_wetlinks import WETLINKS_BUFFER_BYTES, window_cfg
from experiments.slice_wetlinks import OUT_DIR
from leo_cc.ccas import BbrCCA, LeoAwareCCA
from leo_cc.metrics import summarize_result
from leo_cc.sim import run_sim

W1 = OUT_DIR / "w1_enschede_20231110T091227.csv"


def main() -> None:
    cfg = window_cfg(W1, buffer_bytes=WETLINKS_BUFFER_BYTES)
    cfg.duration_s = 25.0
    for name, factory in (
        ("Crest", lambda: LeoAwareCCA()),
        ("Crest+SH", lambda: LeoAwareCCA(use_spike_hold=True)),
        ("BBR", BbrCCA),
    ):
        print(f"probe w1 25s {name} ...", flush=True)
        held: dict = {"cca": None}

        def _factory(f=factory, h=held):
            cca = f()
            h["cca"] = cca
            return cca

        res = run_sim(_factory, cfg=cfg, n_flows=1)
        m = summarize_result(res)[0]
        cca = held["cca"]
        print(
            f"  {name:9s} gp={m.goodput_bps/1e6:.2f}  p95={m.p95_rtt_s*1000:.2f}  "
            f"reconfigs={getattr(cca, 'reconfigs_detected', 0)}  "
            f"sh={getattr(cca, 'spike_holds', 0)}",
            flush=True,
        )


if __name__ == "__main__":
    main()
