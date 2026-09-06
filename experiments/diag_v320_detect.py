#!/usr/bin/env python3
"""v3.20 detect over-fire measure (follow-on to leftover H2).

FillGap + OpenSlot on (Current reproduce path). SoftCeil off. No cook
unless a shadow tighter gate is clearly safe. Official dual-gate bars
stay gp ≥ 75 / p95 ≤ 138.8. Does not bump Current.

Usage:
  python3 -m experiments.diag_v320_detect
  python3 -m experiments.diag_v320_detect --seeds 13 --duration 12
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
from leo_cc.harness import (
    PRODUCT_GP_BAR,
    PRODUCT_P95_BAR,
    PRODUCT_PATH_PROFILE,
    PRODUCT_SEEDS,
    apply_profile,
)
from leo_cc.metrics import summarize_result
from leo_cc.network import LeoPathConfig
from leo_cc.observability import detect_overfire_hook, leftover_scorecard_hook
from leo_cc.sim import SOFT_QIR_ALPHA, run_sim

OUT = ROOT / "results" / "archive" / "20260906-v320-detect" / "diag"


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
        "handovers": list(lres.handovers),
        **snap,
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--seeds", default=",".join(str(s) for s in PRODUCT_SEEDS))
    ap.add_argument("--duration", type=float, default=90.0)
    ap.add_argument(
        "--replay",
        action="store_true",
        help="Rebuild hooks/TABLE from diagnosis.json (no resim)",
    )
    args = ap.parse_args()
    seeds = tuple(int(x) for x in args.seeds.split(",") if x.strip())
    assert PRODUCT_PATH_PROFILE == "starlink_v1"
    assert SOFT_QIR_ALPHA == 0.20
    OUT.mkdir(parents=True, exist_ok=True)
    rows = []
    if args.replay:
        prev = json.loads((OUT / "diagnosis.json").read_text(encoding="utf-8"))
        rows = list(prev["per_seed"])
        args.duration = float(prev.get("duration_s") or args.duration)
        print(f"replay v3.20 detect-overfire from {OUT / 'diagnosis.json'}", flush=True)
    else:
        print(
            f"diag v3.20 detect-overfire starlink_v1 seeds={seeds} "
            f"dur={args.duration} α={SOFT_QIR_ALPHA} FillGap+OpenSlot on SoftCeil off",
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
                f"events={len(row.get('obs_detect_events') or [])}  "
                f"near_last={row.get('obs_detect_near_path_ho')} "
                f"far_last={row.get('obs_detect_far_path_ho')}  "
                f"reasons={row.get('obs_detect_reason_counts')}",
                flush=True,
            )

    leo_gp = sum(r["fillgap_gp"] for r in rows) / len(rows)
    leo_p95 = sum(r["fillgap_p95"] for r in rows) / len(rows)
    bbr_gp = sum(r["bbr_gp"] for r in rows) / len(rows)
    bbr_p95 = sum(r["bbr_p95"] for r in rows) / len(rows)
    leftover = leftover_scorecard_hook(
        leo_snaps=rows,
        leo_gp=leo_gp,
        leo_p95=leo_p95,
        bbr_gp=bbr_gp,
        bbr_p95=bbr_p95,
    )
    detect = detect_overfire_hook(
        leo_snaps=rows,
        handovers_by_seed={int(r["seed"]): list(r["handovers"]) for r in rows},
        leo_gp=leo_gp,
        leo_p95=leo_p95,
        bbr_gp=bbr_gp,
        bbr_p95=bbr_p95,
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
        "softceil_decision": "REJECT",
        "official_bars": {"gp_mean": PRODUCT_GP_BAR, "p95_mean": PRODUCT_P95_BAR},
        "per_seed": rows,
        "leftover_observability": leftover,
        "detect_overfire": detect,
    }
    (OUT / "diagnosis.json").write_text(json.dumps(payload, indent=2), encoding="utf-8")

    abs_gp = "PASS" if leo_gp >= PRODUCT_GP_BAR else "FAIL"
    abs_p95 = "PASS" if leo_p95 <= PRODUCT_P95_BAR else "FAIL"
    table = f"""# v3.20 detect over-fire — synthetic starlink_v1

FillGap + OpenSlot on. SoftCeil off. Duration {args.duration:.0f}s.
Official dual-gate: gp ≥ {PRODUCT_GP_BAR:.0f} / p95 ≤ {PRODUCT_P95_BAR:.1f}.
Current stays v3.17 FillGap. SoftCeil stays REJECT. Not paid.

| seed | FG gp | BBR gp | p95 | path HO | detect | on_loss | fusion | near HO | far HO | far frac | HO recall |
|-----:|------:|-------:|----:|--------:|-------:|--------:|-------:|--------:|-------:|---------:|----------:|
"""
    for p in detect["per_seed"]:
        seed = p["seed"]
        src = next(r for r in rows if r["seed"] == seed)
        far_frac = p["far_frac"] if p["far_frac"] is not None else float("nan")
        recall = p["ho_recall"] if p["ho_recall"] is not None else float("nan")
        src_ct = p.get("source_counts") or {}
        table += (
            f"| {seed} | {src['fillgap_gp']:.2f} | {src['bbr_gp']:.2f} | "
            f"{src['fillgap_p95']:.2f} | {p['path_handovers']} | {p['detects']} | "
            f"{src_ct.get('on_loss', 0)} | {src_ct.get('fusion', 0)} | "
            f"{p['near_n']} | {p['far_n']} | {far_frac:.3f} | {recall:.3f} |\n"
        )
    means = detect["means"]
    table += f"""
Means: gp {leo_gp:.2f} · p95 {leo_p95:.2f} · detect/HO {means.get('detect_over_path_ho')} ·
far frac {means.get('far_frac')} · HO recall {means.get('ho_recall')}.
BBR {bbr_gp:.2f} / {bbr_p95:.2f}.

| Check | Bar | Result |
|-------|-----|--------|
| official gp | ≥ {PRODUCT_GP_BAR:.0f} | {leo_gp:.2f} {abs_gp} |
| official p95 | ≤ {PRODUCT_P95_BAR:.1f} | {leo_p95:.2f} {abs_p95} |
| beats FillGap lock | > 82.45 and p95 ≤ 76.26 | NO — do not bump Current |

H4 most detects far from path HO: {detect['hypotheses']['H4_most_detects_far_from_path_ho']}
H5 tighter gate keeps HO / cuts far: {detect['hypotheses']['H5_tighter_gate_keeps_ho_cuts_far']}
H6 one primary owns half of far: {detect['hypotheses']['H6_one_primary_owns_half_far']}
Promising shadow gates: {detect.get('promising_gates')}
Reason counts: {detect.get('reason_counts_sum')}
Source counts: {detect.get('source_counts_sum')}

{detect.get('recommendation')}
"""
    (OUT / "TABLE.md").write_text(table, encoding="utf-8")
    print("\n=== detect over-fire hook ===")
    print(json.dumps(detect["hypotheses"], indent=2))
    print(json.dumps(detect["means"], indent=2))
    print(json.dumps(detect.get("gates"), indent=2))
    print(detect.get("recommendation"))
    print(table)
    print(f"wrote {OUT / 'diagnosis.json'}")
    print("Current stays v3.17 FillGap. SoftCeil stays REJECT. Not paid.")


if __name__ == "__main__":
    main()
