# LeoAware v3.18 SoftCeil — starlink_v1 leftover after FillGap

**Date:** 2026-09-04  
**Branch:** `cursor/v318-softceil-bee0`  
**Era:** synthetic `starlink_v1` (same harness / seeds as the v3.17 FillGap lock)  
**Lever:** **SoftCeil** (`use_soft_ceil`, default **False**)  
**Decision:** **REJECT vs BBR and vs FillGap Current.** Seed 13 regressed
96.80 → 96.31. Mean 82.35 ≤ BBR 82.44. p95 matched FillGap 76.26. Current
stays v3.17 FillGap. Not paid. Do not bump Current.

## Lock we chased

v3.17 FillGap Current (`results/archive/20260814-v317-fillgap/`):

| CCA | gp mean | p95 mean |
|-----|--------:|---------:|
| BBRv3approx | **82.44** | **76.66** |
| LeoAware v3.17 FillGap (Current) | **82.45** | **76.26** |

FillGap closed the OpenSlot leftover (82.38 → 82.45) but seed 13 was still
**96.80 vs BBR 97.31** (−0.51). Mean edge vs BBR was +0.01. FillGap 0.85 and
OpenSlot 0.80 stayed frozen.

Seeds **13, 7, 42, 99, 123**. `leo_fast_ho` 90s. Soft-QIR α=0.20. Endpoint-only.
Research bar: mean gp > 82.44 AND p95 ≤ 76.26 AND seed 13 ≥ 96.80. Terr ≥ 77.

This is a **synthetic** `starlink_v1` harness, not dish PHY. No `leocc_v1`
numbers in the product table.

## Diagnosis (measured, before the cook)

`python3 -m experiments.diag_v318_softceil`  
Archive: `results/archive/20260904-v318-softceil/diag/diagnosis.json`

FillGap + OpenSlot on (0.85 / 0.80 untouched). SoftCeil off.

| seed | FillGap gp | BBR gp | Δ | softceil elig | cwnd/delBDP | leftover band |
|-----:|-----------:|-------:|--:|--------------:|------------:|--------------:|
| 13 | 96.80 | 97.31 | **−0.52** | **0.201** | 0.93 | 0.203 |
| 7 | 75.36 | 75.08 | +0.28 | 0.184 | 0.95 | 0.188 |
| 42 | 81.25 | 81.25 | +0.00 | 0.148 | 0.99 | 0.149 |
| 99 | 73.19 | 72.98 | +0.21 | 0.196 | 0.96 | 0.198 |
| 123 | 85.61 | 85.57 | +0.05 | 0.182 | 0.97 | 0.185 |

Means: delay-clean 0.925 · delivery-caught 0.948 · leftover band 0.185 ·
SoftCeil-eligible 0.182 · still below 0.85 0.285 · at/above 0.90 0.524 ·
FillGap cwnd 605 KB vs BBR 964 KB · delivery BDP 631 KB.

| Hypothesis | Verdict | Evidence |
|------------|---------|----------|
| **H1** seed 13 leftover is the 0.85–0.90 band | **CONFIRMED as eligibility** | elig 0.201; Δ −0.52 |
| **H2** seeds 7/99/123 do not need SoftCeil | **CONFIRMED** | all three Δ > 0 vs BBR |

The cook then **falsified H1 as a closer**: filling that band hurt seed 13.
Do not retry a 0.85→0.90 (or higher) ceiling raise on this path.

## What SoftCeil is

One named lever. Opt-in. Default **False**.

When the last ACK is delay-clean (`rtt / min_rtt < 1.12`, no high-delay
streak, not in REPROBE, not in CA hold) **and** measured delivery ≥ 0.95 ×
`bw_est` **and** cwnd is in **[0.85×, 0.90×)** delivery BDP, add **1 MSS**,
capped at 0.90×. Fill-family: at most one MSS per ACK (FillGap first).

Never gates `ep:loss_burst`. Does not retune FillGap 0.85 or OpenSlot 0.80.

## Official archive

`python3 -m experiments.run_starlink`

| CCA | gp mean | p95 mean |
|-----|--------:|---------:|
| CUBIC | 8.57 | 71.63 |
| BBRv3approx | **82.44** | 76.66 |
| LeoAware v3.9 Crest (prior lock) | 82.07 | 76.26 |
| LeoAware + OpenSlot (v3.16) | 82.38 | 76.26 |
| LeoAware + FillGap (Current) | **82.45** | **76.26** |
| **LeoAware + SoftCeil** | **82.35** | **76.26** |

Per-seed SoftCeil gp / p95: 13→96.31/72.21 · 7→75.36/67.81 · 42→81.26/97.56 ·
99→73.19/64.09 · 123→85.62/79.65

| seed | SoftCeil | FillGap | BBR |
|-----:|---------:|--------:|----:|
| 13 | **96.31** | 96.80 | 97.31 |
| 7 | 75.36 | 75.36 | 75.08 |
| 42 | 81.26 | 81.25 | 81.25 |
| 99 | 73.19 | 73.19 | 72.98 |
| 123 | 85.62 | 85.61 | 85.57 |

The whole mean drop is seed 13 (−0.49 vs FillGap). Other seeds are flat.
Terr **79.05**. leo_single 83.56 vs BBR 83.32. p95 unchanged (path-tied).

## Gates

| Check | Bar | Result |
|-------|-----|--------|
| gp mean clears BBR | > 82.44 | **82.35 FAIL** |
| p95 mean vs BBR | ≤ 76.66 | **76.26 PASS** |
| seed 13 vs FillGap | ≥ 96.80 | **96.31 FAIL** |
| p95 vs FillGap Current | ≤ 76.26 | **76.26 PASS** (same raw 76.26408) |
| absolute gp / p95 | ≥75 / ≤138.8 | PASS |
| terrestrial | ≥ 77 | **79.05 PASS** |
| seeds | 13,7,42,99,123 | PASS |
| integrity | flag default False | PASS |

**Decision: REJECT vs BBR.** Current stays v3.17 FillGap 82.45 / 76.26.
Default stays `use_soft_ceil=False`. Do not raise the FillGap ceiling next.
The leftover is not the 0.85–0.90 band.

## Integrity

`LeoAwareCCA()` keeps `use_soft_ceil=False`, `use_fill_gap=False`, and
`use_openslot=False`. Default `run_suite` / `multi_seed` stay on the Crest
constructor path. Reproduce Current with `python3 -m experiments.run_starlink
--no-soft-ceil`.

## Reproduce

```bash
python3 -m experiments.test_ascent_d_integrity
python3 -m experiments.test_ope_integrity
python3 -m experiments.diag_v318_softceil
python3 -m experiments.run_starlink
```

Archive: `results/archive/20260904-v318-softceil/`
