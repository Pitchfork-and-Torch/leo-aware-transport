#!/usr/bin/env python3
"""Short w1 probe: Crest vs Crest+SH vs BBR (25s, includes t=12 spike).

Prints cumulative goodput at 1/2/5/12/13/25s so startup tax is visible.
The entire 90s w1 uncap gap (386.98 vs 389.24) lives in the first 25s.
"""
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
MARKS = (1.0, 2.0, 5.0, 12.0, 13.0, 25.0)


def _cum_gp_mbps(log, t_end: float) -> float:
    bits = 0.0
    last_t = 0.0
    for t, gp in zip(log.t, log.goodput_bps):
        if t > t_end + 1e-9:
            break
        dt = t - last_t if t > last_t else 0.05
        bits += gp * dt
        last_t = t
    return bits / max(t_end, 1e-9) / 1e6


def _snap(log, t_mark: float) -> tuple[float, str]:
    cwnd, mode = 0.0, "?"
    for t, c, m in zip(log.t, log.cwnd, log.mode):
        if t > t_mark + 1e-9:
            break
        cwnd, mode = c, m
    return cwnd, mode


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
        log = res.flows[0]
        print(
            f"  {name:9s} gp={m.goodput_bps/1e6:.2f}  p95={m.p95_rtt_s*1000:.2f}  "
            f"reconfigs={getattr(cca, 'reconfigs_detected', 0)}  "
            f"sh={getattr(cca, 'spike_holds', 0)}",
            flush=True,
        )
        parts = []
        for t in MARKS:
            gp = _cum_gp_mbps(log, t)
            cwnd, mode = _snap(log, t)
            parts.append(f"t={t:4.0f} {gp:7.2f} cwnd={cwnd/1e3:7.1f}k {mode}")
        print("   " + " | ".join(parts[:3]), flush=True)
        print("   " + " | ".join(parts[3:]), flush=True)


if __name__ == "__main__":
    main()
