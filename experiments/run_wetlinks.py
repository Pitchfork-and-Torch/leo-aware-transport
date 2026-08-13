#!/usr/bin/env python3
"""v3.11 WetLinks CSV lock: geometry first, then endpoint CCA on 5 windows.

Era: wetlinks_v1. Never mix with starlink_v1 82.09/76.26 or ope_v36 58/152.
Crest stays (LeoAwareCCA defaults). No Halo/QSP/PATHHINT.

Usage:
  python -m experiments.run_wetlinks --geometry-only
  python -m experiments.run_wetlinks --tag 20260813-v311-wetlinks
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

from experiments.slice_wetlinks import DURATION_S, OUT_DIR, WINDOW_SPECS
from leo_cc.ccas import BbrCCA, CubicCCA, LeoAwareCCA
from leo_cc.harness import (
    PRODUCT_GP_BAR,
    PRODUCT_P95_BAR,
    PRODUCT_PATH_PROFILE,
    PRODUCT_SEEDS,
    PRODUCT_TERR_GP_BAR,
)
from leo_cc.metrics import summarize_result
from leo_cc.network import LeoPathConfig, walk_path_geometry
from leo_cc.sim import SOFT_QIR_ALPHA, run_sim

ERA = "wetlinks_v1"
# Product sim slot. CSV files stay at 50 ms samples (path holds).
# dt=0.05 + 250 KB buffer caps send at 8*buffer/dt ≈ 40 Mbps and adds a
# fake 10 ms soft-QIR (α*dt). That is a harness artifact, not a CCA result.
SIM_DT_S = 0.01


def window_paths(trace_dir: Path) -> list[Path]:
    paths = [trace_dir / f"{wid}.csv" for wid, _, _ in WINDOW_SPECS]
    missing = [p for p in paths if not p.exists()]
    if missing:
        raise SystemExit(
            "missing WetLinks windows:\n  "
            + "\n  ".join(str(p) for p in missing)
            + "\nRun: python -m experiments.slice_wetlinks --fetch"
        )
    return paths


def window_cfg(path: Path, dt_s: float = SIM_DT_S) -> LeoPathConfig:
    return LeoPathConfig(
        duration_s=DURATION_S,
        dt_s=dt_s,
        seed=0,
        path_profile=ERA,
        trace_csv=str(path),
    )


def geometry_table(trace_dir: Path) -> pd.DataFrame:
    rows = []
    for path in window_paths(trace_dir):
        g = walk_path_geometry(window_cfg(path))
        g["window_id"] = path.stem
        rows.append(g)
    return pd.DataFrame(rows)


def verdict_from_geometry(df: pd.DataFrame) -> dict:
    oracle_mean = float(df["oracle_gp_mbps"].mean())
    path_p95_mean = float(df["path_p95_ms"].mean())
    cap_w_p95_mean = float(df["cap_weighted_p95_ms"].mean())
    gp_possible = oracle_mean >= PRODUCT_GP_BAR - 1e-9
    p95_possible = min(path_p95_mean, cap_w_p95_mean) <= PRODUCT_P95_BAR + 1e-9
    return {
        "era": ERA,
        "n_windows": int(len(df)),
        "oracle_gp_mean": oracle_mean,
        "path_p95_mean": path_p95_mean,
        "cap_weighted_p95_mean": cap_w_p95_mean,
        "gp_ge_75_possible": gp_possible,
        "p95_le_138_8_possible": p95_possible,
        "absolute_dual_gate_possible": gp_possible and p95_possible,
        "soft_qir_alpha": SOFT_QIR_ALPHA,
        "bars": {"gp_mean": PRODUCT_GP_BAR, "p95_mean": PRODUCT_P95_BAR},
        "note": (
            "Geometry uses hold-expanded WetLinks slices (15s iperf mean + "
            "ping aggregate). Do not mix with starlink_v1 or ope_v36."
        ),
    }


def run_window_cca(trace_dir: Path) -> pd.DataFrame:
    rows = []
    algos = [("CUBIC", CubicCCA), ("BBRv3approx", BbrCCA), ("LeoAware", LeoAwareCCA)]
    for path in window_paths(trace_dir):
        cfg = window_cfg(path)
        for name, cls in algos:
            print(f"cca {path.stem} {name} ...", flush=True)
            res = run_sim(cls, cfg=cfg, n_flows=1)
            m = summarize_result(res)[0]
            rows.append(
                {
                    "era": ERA,
                    "window_id": path.stem,
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


def run_terr_control() -> pd.DataFrame:
    rows = []
    for seed in PRODUCT_SEEDS:
        cfg = LeoPathConfig(duration_s=60, seed=seed, terrestrial=True)
        print(f"cca terrestrial seed={seed} LeoAware ...", flush=True)
        res = run_sim(LeoAwareCCA, cfg=cfg, n_flows=1)
        m = summarize_result(res)[0]
        rows.append(
            {
                "era": "synthetic_terrestrial",
                "window_id": f"terr_seed{seed}",
                "cca": "LeoAware",
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


def scorecard(geo_v: dict, cca_df: pd.DataFrame, terr_df: pd.DataFrame) -> dict:
    def means(df: pd.DataFrame, cca: str) -> tuple[float, float]:
        g = df[df["cca"] == cca]
        return float(g["goodput_mbps"].mean()), float(g["p95_rtt_ms"].mean())

    leo_gp, leo_p95 = means(cca_df, "LeoAware")
    bbr_gp, bbr_p95 = means(cca_df, "BBRv3approx")
    cub_gp, cub_p95 = means(cca_df, "CUBIC")
    terr_gp = float(terr_df["goodput_mbps"].mean())
    terr_p95 = float(terr_df["p95_rtt_ms"].mean())
    gp_ok = leo_gp >= PRODUCT_GP_BAR
    p95_ok = leo_p95 <= PRODUCT_P95_BAR
    terr_ok = terr_gp >= PRODUCT_TERR_GP_BAR
    accept = bool(
        geo_v["absolute_dual_gate_possible"] and gp_ok and p95_ok and terr_ok
    )
    return {
        "era": ERA,
        "product_lock_era": PRODUCT_PATH_PROFILE,
        "decision": "ACCEPT" if accept else "REJECT",
        "soft_qir_alpha": SOFT_QIR_ALPHA,
        "geometry": geo_v,
        "windows": {
            "LeoAware_gp_mean": leo_gp,
            "LeoAware_p95_mean": leo_p95,
            "BBR_gp_mean": bbr_gp,
            "BBR_p95_mean": bbr_p95,
            "CUBIC_gp_mean": cub_gp,
            "CUBIC_p95_mean": cub_p95,
        },
        "terrestrial": {
            "LeoAware_gp_mean": terr_gp,
            "LeoAware_p95_mean": terr_p95,
            "note": "synthetic terrestrial control; not a WetLinks window",
        },
        "gates": {
            "geometry_dual_gate": geo_v["absolute_dual_gate_possible"],
            "gp_ge_75": gp_ok,
            "p95_le_138_8": p95_ok,
            "terr_ge_77": terr_ok,
        },
        "note": (
            "wetlinks_v1 is a new era. Do not mix with starlink_v1 82.09/76.26 "
            "or ope_v36 58/152. Crest defaults unchanged. No Current bump. "
            "Replay uses product dt=0.01; 250 KB buffer send ceiling is "
            f"{8 * 250_000 / SIM_DT_S / 1e6:.0f} Mbps (windows above that "
            "cannot fill even if the iperf mean is higher)."
        ),
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--tag", default="20260813-v311-wetlinks")
    ap.add_argument("--trace-dir", type=Path, default=OUT_DIR)
    ap.add_argument(
        "--geometry-only",
        action="store_true",
        help="walk geometry and stop (no CCA). Use if bars fail.",
    )
    args = ap.parse_args()
    out_dir = ROOT / "results" / "archive" / args.tag
    out_dir.mkdir(parents=True, exist_ok=True)

    geo = geometry_table(args.trace_dir)
    verdict = verdict_from_geometry(geo)
    geo.to_csv(out_dir / "path_geometry.csv", index=False)
    (out_dir / "feasibility_verdict.json").write_text(
        json.dumps(verdict, indent=2), encoding="utf-8"
    )
    print("=== wetlinks_v1 geometry (5 windows) ===")
    cols = [
        "window_id",
        "oracle_gp_mbps",
        "mean_cap_mbps",
        "path_p50_ms",
        "path_p95_ms",
        "path_max_ms",
        "n_ho",
    ]
    print(geo[cols].to_string(index=False, float_format=lambda x: f"{x:.2f}"))
    print(
        f"MEANS  oracle_gp={verdict['oracle_gp_mean']:.2f}  "
        f"path_p95={verdict['path_p95_mean']:.2f}  "
        f"cap_w_p95={verdict['cap_weighted_p95_mean']:.2f}"
    )
    print(
        f"VERDICT  gp≥75 possible={verdict['gp_ge_75_possible']}  "
        f"p95≤138.8 possible={verdict['p95_le_138_8_possible']}  "
        f"absolute dual-gate possible={verdict['absolute_dual_gate_possible']}"
    )

    if not verdict["absolute_dual_gate_possible"]:
        print(
            "STOP: WetLinks geometry fails the absolute bars. "
            "No CCA cook. No quiet rebaseline.",
            flush=True,
        )
        print(f"Wrote {out_dir}")
        return

    if args.geometry_only:
        print("geometry-only: bars possible; skip CCA this invocation")
        print(f"Wrote {out_dir}")
        return

    cca_df = run_window_cca(args.trace_dir)
    terr_df = run_terr_control()
    cca_df.to_csv(out_dir / "window_cca.csv", index=False)
    terr_df.to_csv(out_dir / "terr_control.csv", index=False)
    card = scorecard(verdict, cca_df, terr_df)
    (out_dir / "scorecard.json").write_text(
        json.dumps(card, indent=2), encoding="utf-8"
    )
    print("\n=== 5-window CCA means ===")
    print(
        cca_df.groupby("cca")[["goodput_mbps", "p95_rtt_ms"]]
        .mean()
        .to_string(float_format=lambda x: f"{x:.3f}")
    )
    print(
        f"terr LeoAware gp={card['terrestrial']['LeoAware_gp_mean']:.3f}  "
        f"p95={card['terrestrial']['LeoAware_p95_mean']:.3f}"
    )
    print(f"DECISION {card['decision']}")
    print(f"Wrote {out_dir}")


if __name__ == "__main__":
    main()
