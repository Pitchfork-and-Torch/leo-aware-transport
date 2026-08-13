#!/usr/bin/env python3
"""v3.9 Crest invention ablation on the product path.

Fair leo_fast_ho, same starlink_v1 orbit, seeds 13,7,42,99,123.
Asks whether CA / DLC+LSG / freeze-only anticipator earn their keep vs
plain v3.7-style LeoAware (all Crest flags off). BBR is the same-path
reference. Does not retune bars. Does not bump Current.

Usage:
  python -m experiments.crest_ablation
  python -m experiments.crest_ablation --tag 20260812-v39-crest-ablation
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

from leo_cc.ccas import BbrCCA, LeoAwareCCA
from leo_cc.harness import (
    PRODUCT_GP_BAR,
    PRODUCT_P95_BAR,
    PRODUCT_PATH_PROFILE,
    PRODUCT_SEEDS,
    apply_profile,
    resolve_path_profile,
)
from leo_cc.metrics import summarize_result
from leo_cc.network import LeoPathConfig
from leo_cc.sim import SOFT_QIR_ALPHA, run_sim

RESULTS = ROOT / "results"

# Invention ladder. Anticipator is optional per v3.9 design.
VARIANTS: dict[str, dict] = {
    "BBRv3approx": {"kind": "bbr"},
    "v37_oce": {
        "kind": "leo",
        "use_ca": False,
        "use_dlc": False,
        "use_lsg": False,
        "use_anticipator": False,
    },
    "ca": {
        "kind": "leo",
        "use_ca": True,
        "use_dlc": False,
        "use_lsg": False,
        "use_anticipator": False,
    },
    "ca_dlc_lsg": {
        "kind": "leo",
        "use_ca": True,
        "use_dlc": True,
        "use_lsg": True,
        "use_anticipator": False,
    },
    "v39_full": {
        "kind": "leo",
        "use_ca": True,
        "use_dlc": True,
        "use_lsg": True,
        "use_anticipator": True,
    },
}


def _factory(name: str):
    spec = VARIANTS[name]
    if spec["kind"] == "bbr":
        return BbrCCA
    flags = {k: spec[k] for k in ("use_ca", "use_dlc", "use_lsg", "use_anticipator")}
    return lambda: LeoAwareCCA(**flags)


def fast_ho_cfg(seed: int, path_profile: str) -> LeoPathConfig:
    cfg = LeoPathConfig(
        duration_s=90,
        handover_interval_s=12,
        handover_jitter_s=4,
        seed=seed,
    )
    return apply_profile(cfg, path_profile)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--seeds", default=",".join(str(s) for s in PRODUCT_SEEDS))
    ap.add_argument("--path-profile", default=PRODUCT_PATH_PROFILE)
    ap.add_argument("--tag", default="20260812-v39-crest-ablation")
    ap.add_argument(
        "--variants",
        default=",".join(VARIANTS),
        help="comma-separated variant names",
    )
    args = ap.parse_args()
    path_profile = resolve_path_profile(args.path_profile)
    seeds = [int(x) for x in args.seeds.split(",") if x.strip()]
    variants = [v.strip() for v in args.variants.split(",") if v.strip()]
    unknown = [v for v in variants if v not in VARIANTS]
    if unknown:
        raise SystemExit(f"unknown variants {unknown}; choose from {list(VARIANTS)}")

    print(
        f"crest_ablation era={path_profile}  α={SOFT_QIR_ALPHA}  "
        f"bars gp≥{PRODUCT_GP_BAR} p95≤{PRODUCT_P95_BAR}  variants={variants}",
        flush=True,
    )

    rows = []
    for seed in seeds:
        cfg = fast_ho_cfg(seed, path_profile)
        for name in variants:
            print(f"leo_fast_ho seed={seed} {name} ...", flush=True)
            res = run_sim(_factory(name), cfg=cfg, n_flows=1)
            m = summarize_result(res)[0]
            spec = VARIANTS[name]
            rows.append(
                {
                    "scenario": "leo_fast_ho",
                    "seed": seed,
                    "variant": name,
                    "path_profile": cfg.path_profile,
                    "goodput_mbps": m.goodput_bps / 1e6,
                    "p95_rtt_ms": m.p95_rtt_s * 1000,
                    "p95_path_rtt_ms": m.p95_path_rtt_s * 1000,
                    "p95_excess_rtt_ms": m.p95_excess_rtt_s * 1000,
                    "use_ca": spec.get("use_ca"),
                    "use_dlc": spec.get("use_dlc"),
                    "use_lsg": spec.get("use_lsg"),
                    "use_anticipator": spec.get("use_anticipator"),
                    "handovers": len(res.handovers),
                }
            )

    df = pd.DataFrame(rows)
    out_dir = RESULTS / "archive" / args.tag
    out_dir.mkdir(parents=True, exist_ok=True)
    df.to_csv(out_dir / "crest_ablation_raw.csv", index=False)
    summary = (
        df.groupby("variant")
        .agg(
            goodput_mean=("goodput_mbps", "mean"),
            goodput_std=("goodput_mbps", "std"),
            p95_mean=("p95_rtt_ms", "mean"),
            p95_std=("p95_rtt_ms", "std"),
            p95_path_mean=("p95_path_rtt_ms", "mean"),
            p95_excess_mean=("p95_excess_rtt_ms", "mean"),
            n=("seed", "count"),
        )
        .reset_index()
    )
    summary["gp_ge_75"] = summary["goodput_mean"] >= PRODUCT_GP_BAR
    summary["p95_le_138_8"] = summary["p95_mean"] <= PRODUCT_P95_BAR
    summary["dual_gate"] = summary["gp_ge_75"] & summary["p95_le_138_8"]
    summary.to_csv(out_dir / "crest_ablation_summary.csv", index=False)
    card = {
        "era": path_profile,
        "soft_qir_alpha": SOFT_QIR_ALPHA,
        "seeds": seeds,
        "variants": summary.to_dict(orient="records"),
        "note": (
            "Invention ladder on starlink_v1 leo_fast_ho. "
            "Not a Current bump. Anticipator is optional."
        ),
    }
    (out_dir / "crest_ablation_scorecard.json").write_text(
        json.dumps(card, indent=2), encoding="utf-8"
    )
    print("\n=== Crest ablation means (leo_fast_ho) ===")
    print(summary.to_string(index=False))
    print(f"\nWrote {out_dir}")


if __name__ == "__main__":
    main()
