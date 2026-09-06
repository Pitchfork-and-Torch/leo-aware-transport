#!/usr/bin/env python3
"""v3.19 leftover observability after SoftCeil REJECT.

FillGap + OpenSlot on (Current reproduce path). SoftCeil off. No cook.
Measures cruise vs post-detect leftover and detect/HO over-fire on
synthetic starlink_v1. Does not bump Current.

Usage:
  python3 -m experiments.diag_v319_leftover
  python3 -m experiments.diag_v319_leftover --seeds 13 --duration 12
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from leo_cc.ccas import BbrCCA, LeoAwareCCA
from leo_cc.harness import PRODUCT_PATH_PROFILE, PRODUCT_SEEDS, apply_profile
from leo_cc.metrics import summarize_result
from leo_cc.network import LeoPathConfig
from leo_cc.observability import leftover_scorecard_hook
from leo_cc.sim import SOFT_QIR_ALPHA, run_sim

OUT = ROOT / "results" / "archive" / "20260906-v319-leftover" / "diag"


def _cfg(seed: int, duration_s: float) -> LeoPathConfig:
    return apply_profile(
        LeoPathConfig(
            duration_s=duration_s,
            handover_interval_s=12,
            handover_jitter_s=4,
            seed=seed,
        ),
        PRODUCT_PATH_PROFILE,
    )


def run_seed(seed: int, duration_s: float) -> dict:
    lres = run_sim(
        lambda: LeoAwareCCA(use_openslot=True, use_fill_gap=True, use_soft_ceil=False),
        cfg=_cfg(seed, duration_s),
        n_flows=1,
    )
    bres = run_sim(BbrCCA, cfg=_cfg(seed, duration_s), n_flows=1)
    lm = summarize_result(lres)[0]
    bm = summarize_result(bres)[0]
    snap = lres.cca_snapshots[0]
    return {
        "seed": seed,
        "fillgap_gp": lm.goodput_bps / 1e6,
        "bbr_gp": bm.goodput_bps / 1e6,
        "delta_gp": (lm.goodput_bps - bm.goodput_bps) / 1e6,
        "fillgap_p95": lm.p95_rtt_s * 1000,
        "bbr_p95": bm.p95_rtt_s * 1000,
        "path_handovers": len(lres.handovers),
        **snap,
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--seeds", default=",".join(str(s) for s in PRODUCT_SEEDS))
    ap.add_argument("--duration", type=float, default=90.0)
    args = ap.parse_args()
    seeds = tuple(int(x) for x in args.seeds.split(",") if x.strip())
    assert PRODUCT_PATH_PROFILE == "starlink_v1"
    assert SOFT_QIR_ALPHA == 0.20
    OUT.mkdir(parents=True, exist_ok=True)
    rows = []
    print(
        f"diag v3.19 leftover starlink_v1 seeds={seeds} dur={args.duration} "
        f"α={SOFT_QIR_ALPHA} FillGap+OpenSlot on SoftCeil off",
        flush=True,
    )
    for seed in seeds:
        print(f"seed {seed} ...", flush=True)
        row = run_seed(seed, args.duration)
        rows.append(row)
        print(
            f"  FG {row['fillgap_gp']:.2f} vs BBR {row['bbr_gp']:.2f} "
            f"Δ={row['delta_gp']:+.2f}  ho={row['path_handovers']} "
            f"detect={row['reconfigs_detected']}  "
            f"cruise_band={row['leftover_band_cruise_frac']:.3f} "
            f"post_band={row['leftover_band_post_detect_frac']:.3f} "
            f"ho_band={row['leftover_band_post_path_ho_frac']:.3f} "
            f"below_cruise={row['below_085_cruise_frac']:.3f} "
            f"below_post={row['below_085_post_detect_frac']:.3f} "
            f"below_ho={row['below_085_post_path_ho_frac']:.3f}",
            flush=True,
        )

    hook = leftover_scorecard_hook(
        leo_snaps=rows,
        leo_gp=sum(r["fillgap_gp"] for r in rows) / len(rows),
        leo_p95=sum(r["fillgap_p95"] for r in rows) / len(rows),
        bbr_gp=sum(r["bbr_gp"] for r in rows) / len(rows),
        bbr_p95=sum(r["bbr_p95"] for r in rows) / len(rows),
    )
    payload = {
        "era": "starlink_v1",
        "synthetic": True,
        "soft_qir_alpha": SOFT_QIR_ALPHA,
        "duration_s": args.duration,
        "seeds": list(seeds),
        "fillgap_on": True,
        "openslot_on": True,
        "soft_ceil_on": False,
        "current_paid": False,
        "current_stays": "v3.17 FillGap",
        "per_seed": rows,
        "leftover_observability": hook,
    }
    (OUT / "diagnosis.json").write_text(json.dumps(payload, indent=2), encoding="utf-8")
    means = hook["means"]
    table = f"""# v3.19 leftover observability — synthetic starlink_v1

FillGap + OpenSlot on. SoftCeil off. Duration {args.duration:.0f}s.
Current stays v3.17 FillGap. Not paid.

| seed | FG gp | BBR gp | path HO | detect | cruise band | post-detect band | real-HO band |
|-----:|------:|-------:|--------:|-------:|------------:|-----------------:|-------------:|
"""
    for r in rows:
        table += (
            f"| {r['seed']} | {r['fillgap_gp']:.2f} | {r['bbr_gp']:.2f} | "
            f"{r['path_handovers']} | {r['reconfigs_detected']} | "
            f"{r['leftover_band_cruise_frac']:.3f} | "
            f"{r['leftover_band_post_detect_frac']:.3f} | "
            f"{r['leftover_band_post_path_ho_frac']:.3f} |\n"
        )
    table += f"""
Means: leftover band cruise {means.get('leftover_band_cruise_frac'):.3f} ·
post-detect {means.get('leftover_band_post_detect_frac'):.3f} ·
real path HO {means.get('leftover_band_post_path_ho_frac'):.3f}.
Detect / path HO {hook.get('detect_over_path_ho')}.
Post-detect ACK share {means.get('post_detect_ack_frac'):.3f}
(inflated if detect over-fires). Real path-HO ACK share
{means.get('post_path_ho_ack_frac'):.3f}.

H1 post-detect vs cruise: {hook['hypotheses']['H1_leftover_is_post_detect_not_cruise_band']}
H2 detect over-fire: {hook['hypotheses']['H2_detect_overfires_vs_path_ho']}
H3 leftover band in real HO: {hook['hypotheses']['H3_leftover_band_concentrated_in_real_ho']}
H3b below-0.85 in real HO: {hook['hypotheses']['H3b_below_085_concentrated_in_real_ho']}
"""
    (OUT / "TABLE.md").write_text(table, encoding="utf-8")
    print("\n=== leftover hook ===")
    print(json.dumps(hook["hypotheses"], indent=2))
    print(json.dumps(hook["means"], indent=2))
    print(table)
    print(f"wrote {OUT / 'diagnosis.json'}")
    print("Current stays v3.17 FillGap. Not paid.")


if __name__ == "__main__":
    main()
