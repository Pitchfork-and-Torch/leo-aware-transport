#!/usr/bin/env python3
"""v3.18 product-era cook runner (synthetic starlink_v1).

Same windows/seeds as the v3.9 Crest / v3.17 FillGap lock. SoftCeil is
opt-in for this archive only; LeoAwareCCA() default stays False.
FillGap 0.85 and OpenSlot 0.80 are not retuned; the archive may keep
them on so SoftCeil closes the leftover 0.85-0.90 band.

Usage:
  python3 -m experiments.run_starlink
  python3 -m experiments.run_starlink --no-soft-ceil --no-fill-gap --no-openslot
"""
from __future__ import annotations

import argparse
import csv
import json
import math
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from experiments.multi_seed import scenario_cfg
from leo_cc.ccas import BbrCCA, CubicCCA, LeoAwareCCA
from leo_cc.harness import (
    PRODUCT_GP_BAR,
    PRODUCT_P95_BAR,
    PRODUCT_PATH_PROFILE,
    PRODUCT_SEEDS,
    PRODUCT_TERR_GP_BAR,
)
from leo_cc.metrics import jain_fairness, summarize_result
from leo_cc.sim import SOFT_QIR_ALPHA, run_sim

BBR_GP_LOCK = 82.44
BBR_P95_LOCK = 76.66
CREST_GP_LOCK = 82.07
CREST_P95_LOCK = 76.26
OPENSLOT_GP_LOCK = 82.38
FILLGAP_GP_LOCK = 82.45
FILLGAP_P95_LOCK = 76.26
CREST_SEED13_FLOOR = 96.65
OPENSLOT_SEED13_FLOOR = 96.69
FILLGAP_SEED13_FLOOR = 96.80
TAG = "20260904-v318-softceil"
SCENARIOS = ("leo_fast_ho", "leo_single", "terrestrial")


def _rows(openslot: bool, fill_gap: bool, soft_ceil: bool) -> list[dict]:
    algos = [
        ("CUBIC", lambda: CubicCCA()),
        ("BBRv3approx", lambda: BbrCCA()),
        (
            "LeoAware",
            lambda: LeoAwareCCA(
                use_openslot=openslot,
                use_fill_gap=fill_gap,
                use_soft_ceil=soft_ceil,
            ),
        ),
    ]
    rows: list[dict] = []
    for scen in SCENARIOS:
        for seed in PRODUCT_SEEDS:
            cfg, n_flows = scenario_cfg(scen, seed, PRODUCT_PATH_PROFILE)
            for name, factory in algos:
                print(
                    f"{scen} seed={seed} {name} openslot={openslot} "
                    f"fill_gap={fill_gap} soft_ceil={soft_ceil} ...",
                    flush=True,
                )
                res = run_sim(factory, cfg=cfg, n_flows=n_flows)
                metrics = summarize_result(res)
                thr = [m.goodput_bps for m in metrics]
                fair = jain_fairness(thr) if n_flows > 1 else 1.0
                for m in metrics:
                    rows.append(
                        {
                            "scenario": scen,
                            "seed": seed,
                            "cca": name,
                            "path_profile": cfg.path_profile,
                            "openslot": openslot,
                            "fill_gap": fill_gap,
                            "soft_ceil": soft_ceil,
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
    return rows


def _mean(rows: list[dict], scen: str, cca: str, key: str) -> float:
    xs = [r[key] for r in rows if r["scenario"] == scen and r["cca"] == cca]
    return sum(xs) / len(xs) if xs else float("nan")


def _per_seed(rows: list[dict], scen: str, cca: str) -> list[dict]:
    out = []
    for seed in PRODUCT_SEEDS:
        hit = [r for r in rows if r["scenario"] == scen and r["cca"] == cca and r["seed"] == seed]
        if not hit:
            continue
        r = hit[0]
        out.append(
            {
                "seed": seed,
                "gp": r["goodput_mbps"],
                "p95": r["p95_rtt_ms"],
                "p95_path": r["p95_path_rtt_ms"],
                "p95_excess": r["p95_excess_rtt_ms"],
            }
        )
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--no-openslot", action="store_true", help="OpenSlot off (do not retune 0.80)")
    ap.add_argument("--no-fill-gap", action="store_true", help="Crest/OpenSlot without FillGap")
    ap.add_argument("--no-soft-ceil", action="store_true", help="FillGap/OpenSlot without SoftCeil")
    ap.add_argument("--tag", default=TAG)
    args = ap.parse_args()
    openslot = not args.no_openslot
    fill_gap = not args.no_fill_gap
    soft_ceil = not args.no_soft_ceil
    assert PRODUCT_PATH_PROFILE == "starlink_v1"
    assert SOFT_QIR_ALPHA == 0.20
    assert list(PRODUCT_SEEDS) == [13, 7, 42, 99, 123]

    rows = _rows(openslot, fill_gap, soft_ceil)
    out = ROOT / "results" / "archive" / args.tag
    out.mkdir(parents=True, exist_ok=True)

    csv_path = out / "per_seed_windows.csv"
    with csv_path.open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)

    leo_gp = _mean(rows, "leo_fast_ho", "LeoAware", "goodput_mbps")
    leo_p95 = _mean(rows, "leo_fast_ho", "LeoAware", "p95_rtt_ms")
    bbr_gp = _mean(rows, "leo_fast_ho", "BBRv3approx", "goodput_mbps")
    bbr_p95 = _mean(rows, "leo_fast_ho", "BBRv3approx", "p95_rtt_ms")
    cub_gp = _mean(rows, "leo_fast_ho", "CUBIC", "goodput_mbps")
    cub_p95 = _mean(rows, "leo_fast_ho", "CUBIC", "p95_rtt_ms")
    terr_gp = _mean(rows, "terrestrial", "LeoAware", "goodput_mbps")
    terr_p95 = _mean(rows, "terrestrial", "LeoAware", "p95_rtt_ms")
    single_leo_gp = _mean(rows, "leo_single", "LeoAware", "goodput_mbps")
    single_leo_p95 = _mean(rows, "leo_single", "LeoAware", "p95_rtt_ms")
    single_bbr_gp = _mean(rows, "leo_single", "BBRv3approx", "goodput_mbps")
    single_bbr_p95 = _mean(rows, "leo_single", "BBRv3approx", "p95_rtt_ms")

    seeds_ok = {r["seed"] for r in rows if r["scenario"] == "leo_fast_ho" and r["cca"] == "LeoAware"}
    dropped = [s for s in PRODUCT_SEEDS if s not in seeds_ok]
    per_seed = _per_seed(rows, "leo_fast_ho", "LeoAware")
    seed13 = next((p["gp"] for p in per_seed if p["seed"] == 13), float("nan"))
    seed13_crest_ok = (not math.isnan(seed13)) and seed13 >= CREST_SEED13_FLOOR
    seed13_openslot_ok = (not math.isnan(seed13)) and seed13 >= OPENSLOT_SEED13_FLOOR
    seed13_fillgap_ok = (not math.isnan(seed13)) and seed13 >= FILLGAP_SEED13_FLOOR
    gp_clears = (not math.isnan(leo_gp)) and leo_gp > BBR_GP_LOCK
    p95_ok = (not math.isnan(leo_p95)) and leo_p95 <= BBR_P95_LOCK
    no_fillgap_p95_regress = (not math.isnan(leo_p95)) and leo_p95 <= FILLGAP_P95_LOCK + 1e-9
    terr_ok = (not math.isnan(terr_gp)) and terr_gp >= PRODUCT_TERR_GP_BAR
    abs_gp = leo_gp >= PRODUCT_GP_BAR
    abs_p95 = leo_p95 <= PRODUCT_P95_BAR
    accept = bool(
        gp_clears
        and p95_ok
        and no_fillgap_p95_regress
        and terr_ok
        and seed13_crest_ok
        and seed13_fillgap_ok
        and not dropped
    )
    decision = "ACCEPT" if accept else "REJECT"

    card = {
        "era": PRODUCT_PATH_PROFILE,
        "product_lock_era": PRODUCT_PATH_PROFILE,
        "synthetic": True,
        "soft_qir_alpha": SOFT_QIR_ALPHA,
        "lever": "SoftCeil",
        "use_soft_ceil": soft_ceil,
        "use_fill_gap": fill_gap,
        "use_openslot": openslot,
        "openslot_threshold_untouched": 0.80,
        "fill_gap_ceiling_untouched": 0.85,
        "soft_ceil_ceiling": 0.90,
        "soft_ceil_committed_default": False,
        "fill_gap_committed_default": False,
        "openslot_committed_default": False,
        "seeds": list(PRODUCT_SEEDS),
        "dropped_seeds": dropped,
        "bars": {
            "gp_mean": PRODUCT_GP_BAR,
            "p95_mean": PRODUCT_P95_BAR,
            "terr_gp": PRODUCT_TERR_GP_BAR,
            "bbr_gp_clear": BBR_GP_LOCK,
            "bbr_p95_cap": BBR_P95_LOCK,
            "crest_seed13_floor": CREST_SEED13_FLOOR,
            "openslot_seed13_floor": OPENSLOT_SEED13_FLOOR,
            "fillgap_seed13_floor": FILLGAP_SEED13_FLOOR,
        },
        "leo_fast_ho": {
            "CUBIC_gp_mean": cub_gp,
            "CUBIC_p95_mean": cub_p95,
            "BBR_gp_mean": bbr_gp,
            "BBR_p95_mean": bbr_p95,
            "LeoAware_gp_mean": leo_gp,
            "LeoAware_p95_mean": leo_p95,
            "per_seed": per_seed,
            "bbr_per_seed": _per_seed(rows, "leo_fast_ho", "BBRv3approx"),
            "seed13_gp": seed13,
        },
        "leo_single": {
            "LeoAware_gp_mean": single_leo_gp,
            "LeoAware_p95_mean": single_leo_p95,
            "BBR_gp_mean": single_bbr_gp,
            "BBR_p95_mean": single_bbr_p95,
        },
        "terrestrial": {
            "LeoAware_gp_mean": terr_gp,
            "LeoAware_p95_mean": terr_p95,
            "note": "soft-QIR p95 (path 40 ms + sojourn); not the old path-only 40 ms floor",
        },
        "gates": {
            "gp_clears_bbr_82_44": gp_clears,
            "p95_le_bbr_76_66": p95_ok,
            "gp_ge_75": abs_gp,
            "p95_le_138_8": abs_p95,
            "terr_ge_77": terr_ok,
            "seed13_ge_crest_96_65": seed13_crest_ok,
            "seed13_ge_openslot_96_69": seed13_openslot_ok,
            "seed13_ge_fillgap_96_80": seed13_fillgap_ok,
            "p95_le_fillgap_76_26": no_fillgap_p95_regress,
            "no_seed_dropped": not dropped,
            "product_era": True,
        },
        "decision": decision,
        "current_paid": False,
        "note": (
            "Research-on-product-era only. Synthetic starlink_v1 harness. "
            "Not dish PHY. No leocc numbers. Current stays v3.17 FillGap "
            "unless this cook clearly widens the BBR margin without a p95 "
            "regress. No paid bump."
        ),
    }
    (out / "scorecard.json").write_text(json.dumps(card, indent=2), encoding="utf-8")

    terr_rows = [r for r in rows if r["scenario"] == "terrestrial"]
    with (out / "terr_control.csv").open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=list(terr_rows[0].keys()))
        w.writeheader()
        w.writerows(terr_rows)

    means = f"""# v3.18 SoftCeil means — synthetic starlink_v1

Harness: `python3 -m experiments.run_starlink` (same as v3.9
`multi_seed` seeds 13,7,42,99,123 · 90s · endpoint-only · α=0.20).
**Synthetic** `starlink_v1`. Not dish PHY. No leocc / WetLinks / Zhao numbers.

SoftCeil archive opt-in: `{soft_ceil}`. FillGap archive opt-in: `{fill_gap}`
(0.85 not retuned). OpenSlot archive opt-in: `{openslot}` (0.80 not retuned).
Committed `LeoAwareCCA()` defaults: **False**.

## leo_fast_ho means

| CCA | gp mean | p95 mean |
|-----|--------:|---------:|
| CUBIC | {cub_gp:.2f} | {cub_p95:.2f} |
| BBRv3approx | {bbr_gp:.2f} | {bbr_p95:.2f} |
| LeoAware v3.9 Crest (prior lock) | {CREST_GP_LOCK:.2f} | {CREST_P95_LOCK:.2f} |
| LeoAware + OpenSlot (v3.16) | {OPENSLOT_GP_LOCK:.2f} | {CREST_P95_LOCK:.2f} |
| LeoAware + FillGap (Current) | {FILLGAP_GP_LOCK:.2f} | {FILLGAP_P95_LOCK:.2f} |
| **LeoAware + SoftCeil** | **{leo_gp:.2f}** | **{leo_p95:.2f}** |

BBR lock reference: **{BBR_GP_LOCK:.2f} / {BBR_P95_LOCK:.2f}**.
FillGap Current: **{FILLGAP_GP_LOCK:.2f} / {FILLGAP_P95_LOCK:.2f}**.

## Per-seed LeoAware (leo_fast_ho)

| seed | gp | p95 |
|-----:|---:|----:|
"""
    for p in per_seed:
        means += f"| {p['seed']} | {p['gp']:.2f} | {p['p95']:.2f} |\n"
    means += f"""
Seed 13 floor: Crest {CREST_SEED13_FLOOR:.2f} / OpenSlot {OPENSLOT_SEED13_FLOOR:.2f} / FillGap {FILLGAP_SEED13_FLOOR:.2f} → {seed13:.2f}.

## Other scenarios

| Scenario | LeoAware gp | p95 | note |
|----------|------------:|----:|------|
| leo_single | {single_leo_gp:.2f} | {single_leo_p95:.2f} | BBR {single_bbr_gp:.2f} / {single_bbr_p95:.2f} |
| terrestrial | {terr_gp:.2f} | {terr_p95:.2f} | bar ≥ {PRODUCT_TERR_GP_BAR:.0f} |

## Gates

| Check | Bar | Result |
|-------|-----|--------|
| gp mean clears BBR | > {BBR_GP_LOCK:.2f} | {leo_gp:.2f} {'PASS' if gp_clears else 'FAIL'} |
| p95 mean vs BBR | ≤ {BBR_P95_LOCK:.2f} | {leo_p95:.2f} {'PASS' if p95_ok else 'FAIL'} |
| seed 13 vs Crest lock | ≥ {CREST_SEED13_FLOOR:.2f} | {seed13:.2f} {'PASS' if seed13_crest_ok else 'FAIL'} |
| seed 13 vs OpenSlot | ≥ {OPENSLOT_SEED13_FLOOR:.2f} | {seed13:.2f} {'PASS' if seed13_openslot_ok else 'FAIL'} |
| seed 13 vs FillGap | ≥ {FILLGAP_SEED13_FLOOR:.2f} | {seed13:.2f} {'PASS' if seed13_fillgap_ok else 'FAIL'} |
| p95 vs FillGap Current | ≤ {FILLGAP_P95_LOCK:.2f} | {leo_p95:.2f} {'PASS' if no_fillgap_p95_regress else 'FAIL'} |
| absolute gp | ≥ {PRODUCT_GP_BAR:.0f} | {'PASS' if abs_gp else 'FAIL'} |
| absolute p95 | ≤ {PRODUCT_P95_BAR:.1f} | {'PASS' if abs_p95 else 'FAIL'} |
| terrestrial | ≥ {PRODUCT_TERR_GP_BAR:.0f} | {terr_gp:.2f} {'PASS' if terr_ok else 'FAIL'} |
| seeds | 13,7,42,99,123 | {'PASS' if not dropped else 'FAIL dropped ' + str(dropped)} |

**Decision: {decision} vs BBR.** Research-on-product-era. Current stays v3.17 FillGap unless the margin clearly widens. Not paid.
"""
    (out / "means_tables.md").write_text(means, encoding="utf-8")
    print(means)
    print(json.dumps(card, indent=2))
    print(f"wrote {out}")


if __name__ == "__main__":
    main()
