#!/usr/bin/env python3
"""Step 0 feasibility: can absolute dual-gate (gp≥75 AND p95≤138.8) exist on OPE?

Walks path geometry (no CCA) and optionally runs BBR / LeoAware to show that
ACK p95 is path-dominated. Does not retune CCA. Soft-QIR α is frozen.

Usage:
  python -m experiments.ope_feasibility
  python -m experiments.ope_feasibility --profiles ope_v36,starlink_rtt,starlink_v1
  python -m experiments.ope_feasibility --with-cca --tag 20260812-v38-step0
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
from leo_cc.metrics import summarize_result
from leo_cc.network import LeoPathConfig, generate_synthetic_starlink_trace, walk_path_geometry
from leo_cc.sim import SOFT_QIR_ALPHA, SOFT_QIR_CAP_S, run_sim

SEEDS = (13, 7, 42, 99, 123)
GP_BAR = 75.0
P95_BAR = 138.8


def fast_ho_cfg(seed: int, profile: str) -> LeoPathConfig:
    return LeoPathConfig(
        duration_s=90,
        handover_interval_s=12,
        handover_jitter_s=4,
        seed=seed,
        path_profile=profile,
    )


def geometry_table(profile: str) -> pd.DataFrame:
    rows = []
    for seed in SEEDS:
        g = walk_path_geometry(fast_ho_cfg(seed, profile))
        rows.append(g)
    return pd.DataFrame(rows)


def verdict_from_geometry(df: pd.DataFrame) -> dict:
    oracle_mean = float(df["oracle_gp_mbps"].mean())
    path_p95_mean = float(df["path_p95_ms"].mean())
    cap_w_p95_mean = float(df["cap_weighted_p95_ms"].mean())
    gp_possible = oracle_mean >= GP_BAR - 1e-9
    # ACK p95 ≥ path-base p95 of the samples the CCA actually takes.
    # Capacity-weighted p95 is the full-pipe lower bound on ACK path p95.
    p95_possible = min(path_p95_mean, cap_w_p95_mean) <= P95_BAR + 1e-9
    return {
        "oracle_gp_mean": oracle_mean,
        "path_p95_mean": path_p95_mean,
        "cap_weighted_p95_mean": cap_w_p95_mean,
        "gp_ge_75_possible": gp_possible,
        "p95_le_138_8_possible": p95_possible,
        "absolute_dual_gate_possible": gp_possible and p95_possible,
        "soft_qir_alpha": SOFT_QIR_ALPHA,
        "soft_qir_cap_s": SOFT_QIR_CAP_S,
    }


def run_cca_probe(profile: str) -> pd.DataFrame:
    rows = []
    algos = [("BBRv3approx", BbrCCA), ("LeoAware", LeoAwareCCA)]
    for seed in SEEDS:
        cfg = fast_ho_cfg(seed, profile)
        for name, cls in algos:
            print(f"cca {profile} seed={seed} {name} ...", flush=True)
            res = run_sim(cls, cfg=cfg, n_flows=1)
            m = summarize_result(res)[0]
            rows.append(
                {
                    "profile": profile,
                    "seed": seed,
                    "cca": name,
                    "goodput_mbps": m.goodput_bps / 1e6,
                    "p95_rtt_ms": m.p95_rtt_s * 1000,
                    "p95_path_rtt_ms": m.p95_path_rtt_s * 1000,
                    "p95_excess_rtt_ms": m.p95_excess_rtt_s * 1000,
                    "mean_excess_rtt_ms": m.mean_excess_rtt_s * 1000,
                    "handovers": len(res.handovers),
                    "soft_qir_alpha": res.soft_qir_alpha,
                }
            )
    return pd.DataFrame(rows)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--profiles",
        default="ope_v36,starlink_rtt,starlink_v1",
        help="comma-separated path profiles",
    )
    ap.add_argument(
        "--with-cca",
        action="store_true",
        help="also run BBR + LeoAware (confirms path-dominated p95)",
    )
    ap.add_argument("--tag", default="20260812-v38-step0")
    ap.add_argument("--write-traces", action="store_true")
    args = ap.parse_args()
    profiles = [p.strip() for p in args.profiles.split(",") if p.strip()]
    out_dir = ROOT / "results" / "archive" / args.tag
    out_dir.mkdir(parents=True, exist_ok=True)

    print(
        f"Step 0 feasibility  soft-QIR α={SOFT_QIR_ALPHA} cap={SOFT_QIR_CAP_S*1000:.1f}ms",
        flush=True,
    )
    print(
        f"Product bars (absolute, not relative-BBR): gp≥{GP_BAR} AND p95≤{P95_BAR}",
        flush=True,
    )

    geo_frames = []
    verdicts = {}
    for profile in profiles:
        df = geometry_table(profile)
        geo_frames.append(df)
        v = verdict_from_geometry(df)
        verdicts[profile] = v
        print(f"\n=== path geometry  profile={profile}  seeds={list(SEEDS)} ===")
        cols = [
            "seed",
            "n_ho",
            "mean_cap_mbps",
            "oracle_gp_mbps",
            "path_p50_ms",
            "path_p95_ms",
            "cap_weighted_p95_ms",
            "path_max_ms",
            "frac_cap_ge_75",
        ]
        print(df[cols].to_string(index=False, float_format=lambda x: f"{x:.2f}"))
        print(
            f"MEANS  oracle_gp={v['oracle_gp_mean']:.2f}  "
            f"path_p95={v['path_p95_mean']:.2f}  "
            f"cap_w_p95={v['cap_weighted_p95_mean']:.2f}"
        )
        print(
            f"VERDICT  gp≥75 possible={v['gp_ge_75_possible']}  "
            f"p95≤138.8 possible={v['p95_le_138_8_possible']}  "
            f"absolute dual-gate possible={v['absolute_dual_gate_possible']}"
        )

    geo_all = pd.concat(geo_frames, ignore_index=True)
    geo_all.to_csv(out_dir / "path_geometry.csv", index=False)
    (out_dir / "feasibility_verdict.json").write_text(
        json.dumps(
            {
                "bars": {"gp_mean": GP_BAR, "p95_mean": P95_BAR},
                "soft_qir": {"alpha": SOFT_QIR_ALPHA, "cap_s": SOFT_QIR_CAP_S},
                "seeds": list(SEEDS),
                "profiles": verdicts,
            },
            indent=2,
        ),
        encoding="utf-8",
    )

    if args.with_cca:
        cca_frames = []
        # Default: CCA on the locked OPE profile. Opt-in profiles only if asked.
        cca_profiles = [p for p in profiles if p == "ope_v36"] or profiles[:1]
        for profile in cca_profiles:
            cca_df = run_cca_probe(profile)
            cca_frames.append(cca_df)
            print(f"\n=== CCA probe  profile={profile} ===")
            print(cca_df.to_string(index=False, float_format=lambda x: f"{x:.2f}"))
            for cca, g in cca_df.groupby("cca"):
                print(
                    f"{cca} mean gp={g['goodput_mbps'].mean():.2f}  "
                    f"p95={g['p95_rtt_ms'].mean():.2f}  "
                    f"p95_path={g['p95_path_rtt_ms'].mean():.2f}  "
                    f"p95_excess={g['p95_excess_rtt_ms'].mean():.2f}"
                )
        pd.concat(cca_frames, ignore_index=True).to_csv(
            out_dir / "cca_probe.csv", index=False
        )

    if args.write_traces:
        tdir = ROOT / "traces"
        tdir.mkdir(parents=True, exist_ok=True)
        for profile in profiles:
            generate_synthetic_starlink_trace(
                tdir / f"{profile}_seed13.csv",
                seed=13,
                path_profile=profile,
            )
        print(f"wrote traces under {tdir}")

    locked = verdicts.get("ope_v36", next(iter(verdicts.values())))
    print("\n=== Step 0 decision (ope_v36 research path) ===")
    if not locked["absolute_dual_gate_possible"]:
        print(
            "ope_v36: absolute gp≥75 AND p95≤138.8 is not feasible. "
            "This is the research relative-BBR era, not the product lock. "
            "Product lock is starlink_v1 (see leo_cc/harness.py)."
        )
    else:
        print(
            "Geometry does not forbid the absolute bars on this profile."
        )
    sv1 = verdicts.get("starlink_v1")
    if sv1:
        print(
            f"starlink_v1 product era: oracle_gp={sv1['oracle_gp_mean']:.2f}  "
            f"path_p95={sv1['path_p95_mean']:.2f}  "
            f"absolute dual-gate possible={sv1['absolute_dual_gate_possible']}"
        )
    print(f"Wrote {out_dir}")


if __name__ == "__main__":
    main()
