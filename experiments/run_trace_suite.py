#!/usr/bin/env python3
"""Trace-driven and assisted-path experiments.

Generates a synthetic Starlink-class CSV if missing, then runs:
  - generative leo_fast_ho (endpoint LeoAware)
  - same with use_path_hints + freeze windows
  - CSV replay endpoint-only
  - CSV replay with hints
  - multi-flow fair_mode vs default
"""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from leo_cc.network import LeoPathConfig, generate_synthetic_starlink_trace
from leo_cc.ccas import CubicCCA, BbrCCA, LeoAwareCCA
from leo_cc.sim import run_sim
from leo_cc.metrics import summarize_result, jain_fairness

RESULTS = ROOT / "results"
TRACES = ROOT / "traces"


def main() -> None:
    TRACES.mkdir(parents=True, exist_ok=True)
    RESULTS.mkdir(parents=True, exist_ok=True)
    trace_path = TRACES / "starlink_synthetic_seed13.csv"
    if not trace_path.exists():
        generate_synthetic_starlink_trace(
            trace_path, duration_s=90, dt_s=0.05, seed=13, handover_interval_s=12
        )
        print("wrote", trace_path)

    rows = []

    def run(label, factory, cfg, n_flows=1):
        print("running", label, "...")
        res = run_sim(factory, cfg=cfg, n_flows=n_flows)
        metrics = summarize_result(res)
        thr = [m.goodput_bps for m in metrics]
        fair = jain_fairness(thr) if n_flows > 1 else 1.0
        for m in metrics:
            rows.append(
                {
                    "label": label,
                    "cca": m.name if hasattr(m, "name") else label,
                    "goodput_mbps": m.goodput_bps / 1e6,
                    "p95_rtt_ms": m.p95_rtt_s * 1000,
                    "loss_rate": m.loss_rate,
                    "jain": fair,
                    "handovers": len(res.handovers),
                    "n_flows": n_flows,
                }
            )

    # Fix metric name - FlowMetrics has name field
    # summarize_result returns FlowMetrics with .name

    base = LeoPathConfig(
        duration_s=90, handover_interval_s=12, handover_jitter_s=4, seed=13
    )
    for name, cls in [("CUBIC", CubicCCA), ("BBRv3approx", BbrCCA)]:
        run(f"gen_fast/{name}", lambda c=cls: c(), base)

    run("gen_fast/LeoAware", lambda: LeoAwareCCA(), base)
    run(
        "gen_fast/LeoAware+hints",
        lambda: LeoAwareCCA(use_path_hints=True),
        base,
    )

    tcfg = LeoPathConfig(
        duration_s=90,
        seed=13,
        trace_csv=str(trace_path),
        dt_s=0.05,
    )
    run("trace/LeoAware", lambda: LeoAwareCCA(), tcfg)
    run(
        "trace/LeoAware+hints",
        lambda: LeoAwareCCA(use_path_hints=True),
        tcfg,
    )

    mcfg = LeoPathConfig(duration_s=90, handover_interval_s=25, seed=17)
    run("multi/LeoAware", lambda: LeoAwareCCA(), mcfg, n_flows=3)
    run(
        "multi/LeoAware_fair",
        lambda: LeoAwareCCA(fair_mode=True),
        mcfg,
        n_flows=3,
    )
    run("multi/CUBIC", lambda: CubicCCA(), mcfg, n_flows=3)

    df = pd.DataFrame(rows)
    # fix cca column from metrics
    out = RESULTS / "archive" / "20260811-v3-trace-fair"
    out.mkdir(parents=True, exist_ok=True)
    df.to_csv(out / "trace_fair_summary.csv", index=False)
    print(df.to_string(index=False))
    print("wrote", out)


if __name__ == "__main__":
    main()
