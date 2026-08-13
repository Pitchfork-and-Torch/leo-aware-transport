#!/usr/bin/env python3
"""
Reproducible experiment suite for LEO-aware congestion control.

Product-lock default path is starlink_v1. Research: --path-profile ope_v36.

Usage:
  pip install -r requirements.txt
  python -m experiments.run_suite
  python -m experiments.run_suite --path-profile ope_v36
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd

# Allow running without install
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from leo_cc.network import LeoPathConfig
from leo_cc.ccas import CubicCCA, BbrCCA, LeoAwareCCA
from leo_cc.sim import run_sim
from leo_cc.metrics import summarize_result, jain_fairness
from leo_cc.plotting import plot_timeseries, plot_throughput_latency
from leo_cc.harness import PRODUCT_PATH_PROFILE, apply_profile, resolve_path_profile


RESULTS = ROOT / "results"


def run_scenario(name: str, cca_cls, cfg: LeoPathConfig, n_flows: int = 1):
    res = run_sim(lambda: cca_cls(), cfg=cfg, n_flows=n_flows)
    metrics = summarize_result(res)
    plot_timeseries(res, RESULTS / f"{name}_timeseries.png", title=name)
    return res, metrics


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--path-profile",
        default=PRODUCT_PATH_PROFILE,
        help="starlink_v1 (product lock, default) or ope_v36 (research)",
    )
    args = ap.parse_args()
    path_profile = resolve_path_profile(args.path_profile)
    RESULTS.mkdir(parents=True, exist_ok=True)
    print(f"run_suite path_profile={path_profile}", flush=True)

    scenarios = [
        (
            "leo_single",
            apply_profile(
                LeoPathConfig(
                    duration_s=90, handover_interval_s=22, seed=11, terrestrial=False
                ),
                path_profile,
            ),
            1,
        ),
        (
            "leo_fast_ho",
            apply_profile(
                LeoPathConfig(
                    duration_s=90,
                    handover_interval_s=12,
                    handover_jitter_s=4,
                    seed=13,
                ),
                path_profile,
            ),
            1,
        ),
        (
            "leo_multi",
            apply_profile(
                LeoPathConfig(duration_s=90, handover_interval_s=25, seed=17),
                path_profile,
            ),
            3,
        ),
        (
            "terrestrial",
            LeoPathConfig(duration_s=60, seed=19, terrestrial=True),
            1,
        ),
        (
            "leo_isl",
            apply_profile(
                LeoPathConfig(
                    duration_s=90,
                    handover_interval_s=20,
                    seed=23,
                    isl_enabled=True,
                ),
                path_profile,
            ),
            1,
        ),
    ]

    algos = [
        ("CUBIC", CubicCCA),
        ("BBRv3approx", BbrCCA),
        ("LeoAware", LeoAwareCCA),
    ]

    summary = []
    rows = []
    for scen_name, cfg, n_flows in scenarios:
        for algo_name, cls in algos:
            tag = f"{scen_name}_{algo_name}"
            print(f"running {tag} ...")
            res, metrics = run_scenario(tag, cls, cfg, n_flows=n_flows)
            thr = [m.goodput_bps for m in metrics]
            fair = jain_fairness(thr) if n_flows > 1 else 1.0
            for m in metrics:
                row = {
                    "scenario": scen_name,
                    "cca": algo_name,
                    "path_profile": cfg.path_profile,
                    "flow": m.name,
                    "goodput_mbps": m.goodput_bps / 1e6,
                    "avg_rtt_ms": m.avg_rtt_s * 1000,
                    "p95_rtt_ms": m.p95_rtt_s * 1000,
                    "p99_rtt_ms": m.p99_rtt_s * 1000,
                    "p95_path_rtt_ms": m.p95_path_rtt_s * 1000,
                    "p95_excess_rtt_ms": m.p95_excess_rtt_s * 1000,
                    "loss_rate": m.loss_rate,
                    "utilization": m.utilization,
                    "jain_fairness": fair,
                    "handovers": len(res.handovers),
                }
                summary.append(row)
                rows.append(
                    {
                        "name": f"{algo_name}/{scen_name}",
                        "p95_rtt_ms": row["p95_rtt_ms"],
                        "goodput_mbps": row["goodput_mbps"],
                    }
                )

    df = pd.DataFrame(summary)
    df.to_csv(RESULTS / "summary.csv", index=False)
    (RESULTS / "summary.json").write_text(
        df.to_json(orient="records", indent=2), encoding="utf-8"
    )

    # Pareto for LEO single-flow comparison
    leo_rows = [r for r in rows if "leo_single" in r["name"]]
    if leo_rows:
        plot_throughput_latency(
            leo_rows,
            RESULTS / "leo_single_throughput_latency.png",
            title="LEO single-flow throughput-latency",
        )

    multi = df[df["scenario"] == "leo_multi"]
    if not multi.empty:
        fair_tbl = multi.groupby("cca", as_index=False)["jain_fairness"].first()
        fair_tbl.to_csv(RESULTS / "leo_multi_fairness.csv", index=False)

    print("\n=== Summary (mean by scenario x cca) ===")
    print(
        df.groupby(["scenario", "cca"], as_index=False)[
            ["goodput_mbps", "p95_rtt_ms", "loss_rate"]
        ]
        .mean()
        .to_string(index=False)
    )
    print(f"\nWrote results to {RESULTS}")


if __name__ == "__main__":
    main()
