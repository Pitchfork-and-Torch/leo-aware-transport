#!/usr/bin/env python3
"""Multi-seed robustness harness for LeoAware vs baselines.

Product-lock default is starlink_v1 (absolute gp≥75 AND p95≤138.8).
Research relative-BBR path: --path-profile ope_v36.

Usage:
  python -m experiments.multi_seed
  python -m experiments.multi_seed --path-profile ope_v36
  python -m experiments.multi_seed --seeds 13,7,42,99,123 --scenarios leo_fast_ho
"""
from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from leo_cc.network import LeoPathConfig
from leo_cc.ccas import CubicCCA, BbrCCA, LeoAwareCCA
from leo_cc.sim import SOFT_QIR_ALPHA, run_sim
from leo_cc.metrics import summarize_result, jain_fairness
from leo_cc.harness import (
    PRODUCT_GP_BAR,
    PRODUCT_P95_BAR,
    PRODUCT_PATH_PROFILE,
    PRODUCT_TERR_GP_BAR,
    RESEARCH_PATH_PROFILE,
    apply_profile,
    resolve_path_profile,
)

RESULTS = ROOT / "results"


def scenario_cfg(name: str, seed: int, path_profile: str) -> tuple[LeoPathConfig, int]:
    if name == "leo_fast_ho":
        cfg = LeoPathConfig(
            duration_s=90,
            handover_interval_s=12,
            handover_jitter_s=4,
            seed=seed,
        )
        return apply_profile(cfg, path_profile), 1
    if name == "leo_single":
        cfg = LeoPathConfig(duration_s=90, handover_interval_s=22, seed=seed)
        return apply_profile(cfg, path_profile), 1
    if name == "terrestrial":
        return (LeoPathConfig(duration_s=60, seed=seed, terrestrial=True), 1)
    if name == "leo_multi":
        cfg = LeoPathConfig(duration_s=90, handover_interval_s=25, seed=seed)
        return apply_profile(cfg, path_profile), 3
    raise ValueError(name)


def _scorecard(df: pd.DataFrame, path_profile: str) -> dict:
    fast = df[(df["scenario"] == "leo_fast_ho") & (df["cca"] == "LeoAware")]
    terr = df[(df["scenario"] == "terrestrial") & (df["cca"] == "LeoAware")]
    bbr = df[(df["scenario"] == "leo_fast_ho") & (df["cca"] == "BBRv3approx")]
    gp = float(fast["goodput_mbps"].mean()) if not fast.empty else float("nan")
    p95 = float(fast["p95_rtt_ms"].mean()) if not fast.empty else float("nan")
    p95_path = float(fast["p95_path_rtt_ms"].mean()) if not fast.empty else float("nan")
    p95_ex = float(fast["p95_excess_rtt_ms"].mean()) if not fast.empty else float("nan")
    terr_gp = float(terr["goodput_mbps"].mean()) if not terr.empty else float("nan")
    terr_p95 = float(terr["p95_rtt_ms"].mean()) if not terr.empty else float("nan")
    bbr_gp = float(bbr["goodput_mbps"].mean()) if not bbr.empty else float("nan")
    bbr_p95 = float(bbr["p95_rtt_ms"].mean()) if not bbr.empty else float("nan")
    per_seed = []
    if not fast.empty:
        for seed, g in fast.groupby("seed"):
            per_seed.append(
                {
                    "seed": int(seed),
                    "gp": float(g["goodput_mbps"].mean()),
                    "p95": float(g["p95_rtt_ms"].mean()),
                    "p95_path": float(g["p95_path_rtt_ms"].mean()),
                    "p95_excess": float(g["p95_excess_rtt_ms"].mean()),
                }
            )
    gp_ok = (not math.isnan(gp)) and gp >= PRODUCT_GP_BAR
    p95_ok = (not math.isnan(p95)) and p95 <= PRODUCT_P95_BAR
    terr_ok = (not math.isnan(terr_gp)) and terr_gp >= PRODUCT_TERR_GP_BAR
    product_era = path_profile == PRODUCT_PATH_PROFILE
    accept = bool(product_era and gp_ok and p95_ok and terr_ok)
    decision = "ACCEPT" if accept else "REJECT/WIP"
    return {
        "era": path_profile,
        "product_lock_era": PRODUCT_PATH_PROFILE,
        "research_era": RESEARCH_PATH_PROFILE,
        "soft_qir_alpha": SOFT_QIR_ALPHA,
        "bars": {
            "gp_mean": PRODUCT_GP_BAR,
            "p95_mean": PRODUCT_P95_BAR,
            "terr_gp": PRODUCT_TERR_GP_BAR,
        },
        "leo_fast_ho": {
            "LeoAware_gp_mean": gp,
            "LeoAware_p95_mean": p95,
            "LeoAware_p95_path_mean": p95_path,
            "LeoAware_p95_excess_mean": p95_ex,
            "BBR_gp_mean": bbr_gp,
            "BBR_p95_mean": bbr_p95,
            "per_seed": per_seed,
        },
        "terrestrial": {
            "LeoAware_gp_mean": terr_gp,
            "LeoAware_p95_mean": terr_p95,
            "note": "soft-QIR p95 (path 40 ms + sojourn); not the old path-only 40 ms floor",
        },
        "gates": {
            "gp_ge_75": gp_ok,
            "p95_le_138_8": p95_ok,
            "terr_ge_77": terr_ok,
            "product_era": product_era,
        },
        "decision": decision,
        "note": (
            "Absolute dual-gate is the product lock on starlink_v1 only. "
            "ope_v36 remains research relative-BBR. Do not mix eras."
        ),
    }


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
    ap.add_argument(
        "--path-profile",
        default=PRODUCT_PATH_PROFILE,
        help="starlink_v1 (product lock, default) or ope_v36 (research)",
    )
    ap.add_argument(
        "--openslot",
        action="store_true",
        help="opt in v3.16 OpenSlot on LeoAware (default Crest path stays off)",
    )
    args = ap.parse_args()
    path_profile = resolve_path_profile(args.path_profile)
    seeds = [int(x) for x in args.seeds.split(",") if x.strip()]
    scenarios = [s.strip() for s in args.scenarios.split(",") if s.strip()]
    algos = [
        ("CUBIC", lambda: CubicCCA()),
        ("BBRv3approx", lambda: BbrCCA()),
        ("LeoAware", lambda: LeoAwareCCA(use_openslot=bool(args.openslot))),
    ]
    if "leo_multi" in scenarios:
        algos.append(("LeoAware_fair", lambda: LeoAwareCCA(fair_mode=True)))

    print(
        f"multi_seed era={path_profile}  product_lock={PRODUCT_PATH_PROFILE}  "
        f"soft-QIR α={SOFT_QIR_ALPHA}  bars gp≥{PRODUCT_GP_BAR} p95≤{PRODUCT_P95_BAR}  "
        f"openslot={bool(args.openslot)}",
        flush=True,
    )

    rows = []
    for scen in scenarios:
        for seed in seeds:
            cfg, n_flows = scenario_cfg(scen, seed, path_profile)
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
                            "path_profile": cfg.path_profile,
                            "goodput_mbps": m.goodput_bps / 1e6,
                            "avg_rtt_ms": m.avg_rtt_s * 1000,
                            "p95_rtt_ms": m.p95_rtt_s * 1000,
                            "p99_rtt_ms": m.p99_rtt_s * 1000,
                            "p95_path_rtt_ms": m.p95_path_rtt_s * 1000,
                            "p95_excess_rtt_ms": m.p95_excess_rtt_s * 1000,
                            "mean_excess_rtt_ms": m.mean_excess_rtt_s * 1000,
                            "loss_rate": m.loss_rate,
                            "jain_fairness": fair,
                            "handovers": len(res.handovers),
                        }
                    )

    df = pd.DataFrame(rows)
    out_dir = RESULTS / "archive" / args.tag
    out_dir.mkdir(parents=True, exist_ok=True)
    df.to_csv(out_dir / "multi_seed_raw.csv", index=False)
    summary = (
        df.groupby(["scenario", "cca"])
        .agg(
            goodput_mean=("goodput_mbps", "mean"),
            goodput_std=("goodput_mbps", "std"),
            p95_mean=("p95_rtt_ms", "mean"),
            p95_std=("p95_rtt_ms", "std"),
            p95_path_mean=("p95_path_rtt_ms", "mean"),
            p95_excess_mean=("p95_excess_rtt_ms", "mean"),
            loss_mean=("loss_rate", "mean"),
            n=("seed", "count"),
        )
        .reset_index()
    )
    summary.to_csv(out_dir / "multi_seed_summary.csv", index=False)
    (out_dir / "multi_seed_raw.json").write_text(
        df.to_json(orient="records", indent=2), encoding="utf-8"
    )
    card = _scorecard(df, path_profile)
    (out_dir / "scorecard.json").write_text(
        json.dumps(card, indent=2), encoding="utf-8"
    )
    print("\n=== Multi-seed means ===")
    print(summary.to_string(index=False))
    print("\n=== Product scorecard ===")
    print(json.dumps(card, indent=2))
    print(f"\nWrote {out_dir}")


if __name__ == "__main__":
    main()
