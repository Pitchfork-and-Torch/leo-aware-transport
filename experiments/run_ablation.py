#!/usr/bin/env python3
"""
Ablation matrix: endpoint-only vs ASCENT / ASCENT-D vs OrbCC hybrid.

Usage:
  python -m experiments.run_ablation
  python -m experiments.run_ablation --seeds 13,7,42 --fast

Variants:
  endpoint          LeoAware endpoint-only
  ascent_plain      + unprotected ASCENT path hints
  ascent_d          + ASCENT-D protected hints (erase-on-fail)
  ascent_d_noisy    + ASCENT-D with bit-flip noise (should erase, not act)
  orb               + synthetic OrbCC signals
  hybrid            + ASCENT-D + OrbCC
  bbr / cubic       baselines
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
from leo_cc.harness import PRODUCT_PATH_PROFILE, apply_profile, resolve_path_profile


RESULTS = ROOT / "results" / "ablation"


def _factory(variant: str):
    if variant == "cubic":
        return CubicCCA, dict(path_hint_mode="none", use_orb_telemetry=False)
    if variant == "bbr":
        return BbrCCA, dict(path_hint_mode="none", use_orb_telemetry=False)
    if variant == "endpoint":
        return (
            lambda: LeoAwareCCA(use_path_hints=False, use_orb_signals=False),
            dict(path_hint_mode="none", use_orb_telemetry=False),
        )
    if variant == "ascent_plain":
        return (
            lambda: LeoAwareCCA(use_path_hints=True, use_orb_signals=False),
            dict(path_hint_mode="ascent_plain", use_orb_telemetry=False),
        )
    if variant == "ascent_d":
        return (
            lambda: LeoAwareCCA(use_path_hints=True, use_orb_signals=False),
            dict(path_hint_mode="ascent_d", ascent_bit_flips=0, use_orb_telemetry=False),
        )
    if variant == "ascent_d_noisy":
        return (
            lambda: LeoAwareCCA(use_path_hints=True, use_orb_signals=False),
            dict(path_hint_mode="ascent_d", ascent_bit_flips=64, use_orb_telemetry=False),
        )
    if variant == "orb":
        return (
            lambda: LeoAwareCCA(use_path_hints=False, use_orb_signals=True),
            dict(path_hint_mode="none", use_orb_telemetry=True),
        )
    if variant == "hybrid":
        return (
            lambda: LeoAwareCCA(use_path_hints=True, use_orb_signals=True),
            dict(path_hint_mode="ascent_d", ascent_bit_flips=0, use_orb_telemetry=True),
        )
    raise ValueError(f"unknown variant: {variant}")


def run_one(variant: str, cfg: LeoPathConfig, scenario: str) -> dict:
    cca_factory, sim_kw = _factory(variant)
    res = run_sim(cca_factory, cfg=cfg, n_flows=1, **sim_kw)
    metrics = summarize_result(res)
    m = metrics[0]
    row = {
        "scenario": scenario,
        "variant": variant,
        "seed": cfg.seed,
        "goodput_mbps": m.goodput_bps / 1e6,
        "avg_rtt_ms": m.avg_rtt_s * 1000,
        "p95_rtt_ms": m.p95_rtt_s * 1000,
        "p99_rtt_ms": m.p99_rtt_s * 1000,
        "loss_rate": m.loss_rate,
        "utilization": m.utilization,
        "handovers": len(res.handovers),
        "ascent_ok": res.ascent_ingest.ok if res.ascent_ingest else 0,
        "ascent_erased": res.ascent_ingest.erased if res.ascent_ingest else 0,
        "ascent_applied": res.ascent_ingest.applied if res.ascent_ingest else 0,
        "orb_samples": res.orb_samples,
    }
    cca = res.flows[0]
    # detection lag proxy: first REPROBE-like mode after first handover (if logged)
    return row


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--seeds", default="13,7,42", help="comma-separated seeds")
    ap.add_argument("--fast", action="store_true", help="shorter duration")
    ap.add_argument(
        "--variants",
        default="endpoint,ascent_plain,ascent_d,ascent_d_noisy,orb,hybrid,bbr,cubic",
    )
    ap.add_argument(
        "--path-profile",
        default=PRODUCT_PATH_PROFILE,
        help="starlink_v1 (product lock, default) or ope_v36 (research)",
    )
    args = ap.parse_args()
    path_profile = resolve_path_profile(args.path_profile)
    seeds = [int(x) for x in args.seeds.split(",") if x.strip()]
    variants = [v.strip() for v in args.variants.split(",") if v.strip()]
    duration = 45.0 if args.fast else 90.0

    scenarios = [
        (
            "leo_fast_ho",
            lambda seed: apply_profile(
                LeoPathConfig(
                    duration_s=duration,
                    handover_interval_s=12,
                    handover_jitter_s=4,
                    seed=seed,
                ),
                path_profile,
            ),
        ),
        (
            "leo_single",
            lambda seed: apply_profile(
                LeoPathConfig(
                    duration_s=duration,
                    handover_interval_s=22,
                    seed=seed,
                ),
                path_profile,
            ),
        ),
        (
            "terrestrial",
            lambda seed: LeoPathConfig(
                duration_s=min(60.0, duration),
                seed=seed,
                terrestrial=True,
            ),
        ),
    ]

    RESULTS.mkdir(parents=True, exist_ok=True)
    rows = []
    for scen_name, cfg_fn in scenarios:
        for seed in seeds:
            for var in variants:
                print(f"ablation {scen_name} seed={seed} {var} ...")
                cfg = cfg_fn(seed)
                row = run_one(var, cfg, scen_name)
                rows.append(row)
                print(
                    f"  gp={row['goodput_mbps']:.2f} p95={row['p95_rtt_ms']:.1f} "
                    f"erased={row['ascent_erased']} applied={row['ascent_applied']}"
                )

    df = pd.DataFrame(rows)
    raw_path = RESULTS / "ablation_raw.csv"
    df.to_csv(raw_path, index=False)

    # Aggregate means
    agg = (
        df.groupby(["scenario", "variant"], as_index=False)
        .agg(
            goodput_mean=("goodput_mbps", "mean"),
            goodput_std=("goodput_mbps", "std"),
            p95_mean=("p95_rtt_ms", "mean"),
            p95_std=("p95_rtt_ms", "std"),
            loss_mean=("loss_rate", "mean"),
            erased_mean=("ascent_erased", "mean"),
            applied_mean=("ascent_applied", "mean"),
        )
        .sort_values(["scenario", "variant"])
    )
    summary_path = RESULTS / "ablation_summary.csv"
    agg.to_csv(summary_path, index=False)
    (RESULTS / "ablation_raw.json").write_text(
        df.to_json(orient="records", indent=2), encoding="utf-8"
    )
    print("\n=== ablation summary ===")
    print(agg.to_string(index=False))
    print(f"\nwrote {raw_path}")
    print(f"wrote {summary_path}")


if __name__ == "__main__":
    main()
