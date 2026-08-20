# LeoAware v3.17 FillGap — starlink_v1 product-era cook

**Date:** 2026-08-14  
**Branch:** `cursor/v317-fillgap-0208`  
**Era:** synthetic `starlink_v1` (same harness / seeds as the v3.9 Crest lock)  
**Lever:** **FillGap** (`use_fill_gap`, default **False**)  
**Decision:** **ACCEPT vs BBR** (82.45 > 82.44; p95 76.26 ≤ 76.66; terr 79.05;
seed 13 96.80). **Promoted 2026-08-20 to Current / product dual-gate lock**
(PR #22 landed; constructor defaults stay False).

## Lock we are chasing

v3.9 Crest lock (`results/archive/20260812-v39-starlink-v1/`):

| CCA | gp mean | p95 mean |
|-----|--------:|---------:|
| BBRv3approx | **82.44** | **76.66** |
| LeoAware v3.9 Crest | 82.07 | 76.26 |

v3.16 OpenSlot (PR #21, draft, SHA `7a222fb1`, do not merge):

| CCA | gp mean | p95 mean |
|-----|--------:|---------:|
| LeoAware + OpenSlot | 82.38 | 76.26 |

OpenSlot closed ~0.29 of the 0.37 pace gap. Seeds 7/99/123 beat BBR. Seed 13
leftover **96.69 vs BBR 97.31** is a **cwnd** gap, not pace. Unconstrained
unbind and 2.5× burst already killed (seed 13 → 96.20 / 96.15). Do not revive
those. Do not retune OpenSlot 0.80.

Seeds **13, 7, 42, 99, 123**. `leo_fast_ho` 90s. Soft-QIR α=0.20. Endpoint-only.
Research bar: **mean gp > 82.44 AND p95 ≤ 76.66**. Terr ≥ 77. Seed 13 must
not fall below Crest **96.65** or OpenSlot **96.69**. Means, not peaks.

This is a **synthetic** `starlink_v1` harness, not dish PHY. No `leocc_v1`
numbers in the product table.

## Diagnosis (measured)

`python3 -m experiments.diag_v317_fillgap`  
Archive: `results/archive/20260814-v317-fillgap/diag/diagnosis.json`

OpenSlot left on (0.80 untouched). Same five seeds.

| seed | OpenSlot gp | BBR gp | Δ | fillgap eligible | cwnd / del BDP | cwnd OS/BBR |
|-----:|------------:|-------:|--:|-----------------:|---------------:|------------:|
| 13 | 96.69 | 97.31 | **−0.62** | **0.607** | **0.80** | 0.55 |
| 7 | 75.34 | 75.08 | +0.26 | 0.594 | 0.81 | 0.52 |
| 42 | 81.15 | 81.25 | −0.10 | 0.527 | 0.86 | 0.52 |
| 99 | 73.12 | 72.98 | +0.14 | 0.670 | 0.81 | 0.54 |
| 123 | 85.61 | 85.57 | +0.05 | 0.632 | 0.83 | 0.54 |

Means: delay-clean 0.925 · delivery-caught 0.948 · cwnd below del-BDP 0.652 ·
FillGap-eligible 0.606 · OpenSlot cwnd 516 KB vs BBR 964 KB · delivery BDP
630 KB · inflight OS 254 KB vs BBR 162 KB.

| Hypothesis | Verdict | Evidence |
|------------|---------|----------|
| **H1** seed 13 leftover is cwnd below delivery BDP after a clean path | **CONFIRMED** | eligible 0.607; cwnd/delBDP 0.80; Δ −0.62 |
| **H2** seeds 7/99/123 do not *need* FillGap (already beat BBR) | **CONFIRMED** | all three Δ > 0 vs BBR. They are still eligible (~0.60) so the fill must stay small. |

Seed 42 is a small leftover (−0.10) and sits at 0.86× del BDP (just above the
0.85 gate on the mean). Not the cook target.

## What FillGap is

One named lever. Opt-in. Default **False**.

When the last ACK is delay-clean (`rtt / min_rtt < 1.12`, no high-delay
streak, not in REPROBE, not in CA hold) **and** measured delivery ≥ 0.95 ×
`bw_est` **and** cwnd < 0.85 × delivery BDP (`delivery × min_rtt / 8`), add
**1 MSS**, capped at the 0.85× ceiling. One packet. Not a burst.

Not a pace unbind. Not a burst. Does not retune OpenSlot 0.80. Never gates
`ep:loss_burst`.

FillGap does **not**:

- skip REPROBE / fade-on-reconfig
- raise the p82 filter (CCH / Pulse / p90 — rejected)
- invert sojourn into a pace discount (QSP — rejected)
- special-case `reconfigs_detected==0` or a first-epoch window (SpikeHold)
- generalize FarHold / FastExit / LeanCatch / Halo / PATHHINT
- revive unconstrained unbind or 2.5× burst

## Integrity

`LeoAwareCCA()` keeps `use_fill_gap=False` and `use_openslot=False`. Default
`run_suite` / `multi_seed` stay on the Crest constructor path. Current
scorecard numbers are from `python3 -m experiments.run_starlink`, which opts
in FillGap (and keeps OpenSlot on, 0.80 untouched).

## Official archive

`python3 -m experiments.run_starlink`

| CCA | gp mean | p95 mean |
|-----|--------:|---------:|
| CUBIC | 8.57 | 71.63 |
| BBRv3approx | **82.44** | 76.66 |
| LeoAware v3.9 Crest (prior lock) | 82.07 | 76.26 |
| LeoAware + OpenSlot (v3.16) | 82.38 | 76.26 |
| **LeoAware + FillGap (Current)** | **82.45** | **76.26** |

Per-seed: 13→96.80/72.21 · 7→75.36/67.81 · 42→81.25/97.56 · 99→73.19/64.09 ·
123→85.61/79.65. Terr **79.05**. leo_single 83.56 vs BBR 83.32.

**Decision: ACCEPT vs BBR.** Promoted to **Current / product dual-gate lock**.
Default stays False. Reproduce Current with `python3 -m experiments.run_starlink`.

## Reproduce

```bash
python3 -m experiments.test_ascent_d_integrity
python3 -m experiments.test_ope_integrity
python3 -m experiments.diag_v317_fillgap
python3 -m experiments.run_starlink
```

Archive: `results/archive/20260814-v317-fillgap/`
