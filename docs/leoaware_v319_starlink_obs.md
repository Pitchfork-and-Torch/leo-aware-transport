# LeoAware v3.19 — Starlink leftover observability

**Date:** 2026-09-06  
**Branch:** `cursor/starlink-leftover-obs-1989`  
**Era:** synthetic `starlink_v1`  
**Lever:** none (observe only)  
**Decision:** **research hooks only.** Current stays v3.17 FillGap
82.45 / 76.26. SoftCeil stays REJECT. Not paid.

## Why this exists

v3.18 SoftCeil filled the 0.85–0.90 delivery-BDP band and **lost**
(82.35 vs FillGap 82.45 / BBR 82.44). Seed 13 fell 96.80 → 96.31.
The leftover after FillGap is **not** that cruise band. Do not retry a
ceiling raise.

The next cook needs a measured split, not another one-off diag.
These hooks put leftover counters on the official scorecard:

- cruise vs post-detect vs REPROBE ACK share
- leftover-band and still-below-0.85 share in each region
- LSG clamps by region
- detect count vs real path HOs
- path-HO observe is fail-closed (never REPROBE / detect / fill)

## Measured (FillGap + OpenSlot, SoftCeil off)

`python3 -m experiments.diag_v319_leftover`  
Archive: `results/archive/20260906-v319-leftover/diag/`

Same 90s seeds as the FillGap lock. gp / p95 match Current (seed 13 96.80 vs BBR 97.31).

| seed | path HO | detect | cruise band | post-detect band | real-HO band |
|-----:|--------:|-------:|------------:|-----------------:|-------------:|
| 13 | 7 | 56 | 0.030 | 0.177 | 0.020 |
| 7 | 8 | 56 | 0.029 | 0.164 | 0.020 |
| 42 | 7 | 56 | 0.022 | 0.131 | 0.018 |
| 99 | 7 | 56 | 0.032 | 0.171 | 0.022 |
| 123 | 8 | 57 | 0.024 | 0.166 | 0.014 |

| Hypothesis | Verdict | Evidence |
|------------|---------|----------|
| **H1** leftover band is post-detect, not cruise | **CONFIRMED, weak** | post-detect 0.162 vs cruise 0.027, but post-detect is **86% of ACKs** because detect over-fires |
| **H2** detect over-fires vs real path HO | **CONFIRMED** | ~56 detects vs 7–8 HOs (~8×) |
| **H3** leftover 0.85–0.90 band sits in real HO windows | **DISCARDED** | real-HO band share 0.019 / leftover 0.189 ≈ ACK share 0.107 |
| **H3b** still-below-0.85 sits in real HO windows | **PARTIAL** | 0.046 / 0.277 vs ACK share 0.107 (just over the 1.5× bar) |

SoftCeil was looking at a cruise-band minority. The load-bearing leftover signal is **detect over-fire**, not another 0.85–0.90 fill. Do not cook a detect-cooldown retune in this PR.

## What did not change

- `LeoAwareCCA()` defaults stay FillGap / OpenSlot / SoftCeil **False**
- Dual-gate bars stay gp ≥ 75 and p95 ≤ 138.8
- Soft-QIR α stays 0.20
- No new send-control lever
- No Current / paid bump

## Reproduce

```bash
python3 -m experiments.test_starlink_observability
python3 -m experiments.test_ope_integrity
python3 -m experiments.diag_v319_leftover
```

Official Current reproduce is still `python3 -m experiments.run_starlink --no-soft-ceil`.
That runner now also writes a `leftover_observability` section on the
scorecard. The section is research-only.

Design archive: `results/archive/20260906-v319-leftover/`
