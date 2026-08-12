#!/usr/bin/env python3
"""Multi-seed robustness harness for LeoAware vs baselines.

Usage:
  python -m experiments.multi_seed
  python -m experiments.multi_seed --seeds 13,7,42,99,123 --scenario leo_fast_ho
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from leo_cc.network import LeoPathConfig
from leo_cc.ccas import CubicCCA, BbrCCA, LeoAwareCCA
from leo_cc.sim import run_sim
from leo_cc.metrics import summarize_result, jain_fairness

RESULTS = ROOT / "results"


def scenario_cfg(name: str, seed: int) -> tuple[LeoPathConfig, int]:
    if name == "leo_fast_ho":
        return (
            LeoPathConfig(
                duration_s=90,
                handover_interval_s=12,
                handover_jitter_s=4,
                seed=seed,
            ),
            1,
        )
    if name == "leo_single":
        return (
            LeoPathConfig(duration_s=90, handover_interval_s=22, seed=seed),
            1,
        )
    if name == "terrestrial":
        return (LeoPathConfig(duration_s=60, seed=seed, terrestrial=True), 1)
    if name == "leo_multi":
        return (
            LeoPathConfig(duration_s=90, handover_interval_s=25, seed=seed),
            3,
        )
    raise ValueError(name)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--seeds",
        default="13,7,42,99,123",
        help="comma-separated seeds",
    )
    ap.add_argument(
        "--scenarios",
        default="leo_fast_ho,leo_single,terrestrial",
        help="comma-separated scenarios",
    )
    ap.add_argument("--tag", default="current", help="output tag for archive")
    args = ap.parse_args()
    seeds = [int(x) for x in args.seeds.split(",") if x.strip()]
    scenarios = [s.strip() for s in args.scenarios.split(",") if s.strip()]
    algos = [
        ("CUBIC", lambda: CubicCCA()),
        ("BBRv3approx", lambda: BbrCCA()),
        ("LeoAware", lambda: LeoAwareCCA()),
    ]
    if "leo_multi" in scenarios:
        algos.append(("LeoAware_fair", lambda: LeoAwareCCA(fair_mode=True)))

    rows = []
    for scen in scenarios:
        for seed in seeds:
            cfg, n_flows = scenario_cfg(scen, seed)
            for algo_name, factory in algos:
                if algo_name == "LeoAware_fair" and n_flows < 2:
                    continue
                print(f"{scen} seed={seed} {algo_name} ...", flush=True)
                res = run_sim(factory, cfg=cfg, n_flows=n_flows)
                metrics = summarize_result(res)
                thr = [m.goodput_bps for m in metrics]
                fair = jain_fairness(thr) if n_flows > 1 else 1.0
                for m in metrics:
                    rows.append(
                        {
                            "scenario": scen,
                            "seed": seed,
                            "cca": algo_name,
                            "goodput_mbps": m.goodput_bps / 1e6,
                            "avg_rtt_ms": m.avg_rtt_s * 1000,
                            "p95_rtt_ms": m.p95_rtt_s * 1000,
                            "p99_rtt_ms": m.p99_rtt_s * 1000,
                            "loss_rate": m.loss_rate,
                            "jain_fairness": fair,
                            "handovers": len(res.handovers),
                        }
                    )

    df = pd.DataFrame(rows)
    out_dir = RESULTS / "archive" / args.tag
    out_dir.mkdir(parents=True, exist_ok=True)
    df.to_csv(out_dir / "multi_seed_raw.csv", index=False)
    agg = (
        df.groupby(["scenario", "cca"], as_index=False)[
            ["goodput_mbps", "p95_rtt_ms", "loss_rate"]
        ]
        .agg(["mean", "std", "min", "max"])
    )
    # flatten columns
    agg.columns = [
        "_".join(c).strip("_") if isinstance(c, tuple) else c for c in agg.columns
    ]
    # groupby may produce multiindex - simpler approach:
    summary = (
        df.groupby(["scenario", "cca"])
        .agg(
            goodput_mean=("goodput_mbps", "mean"),
            goodput_std=("goodput_mbps", "std"),
            p95_mean=("p95_rtt_ms", "mean"),
            p95_std=("p95_rtt_ms", "std"),
            loss_mean=("loss_rate", "mean"),
            n=("seed", "count"),
        )
        .reset_index()
    )
    summary.to_csv(out_dir / "multi_seed_summary.csv", index=False)
    (out_dir / "multi_seed_raw.json").write_text(
        df.to_json(orient="records", indent=2), encoding="utf-8"
    )
    print("\n=== Multi-seed means ===")
    print(summary.to_string(index=False))
    print(f"\nWrote {out_dir}")


if __name__ == "__main__":
    main()
