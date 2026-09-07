# LeoAware v3.20 — detect over-fire measure

**Date:** 2026-09-06  
**Branch:** `cursor/detect-overfire-2daf`  
**Era:** synthetic `starlink_v1`  
**Lever:** none (observe + shadow gates)  
**Decision:** **observe-only.** Current stays v3.17 FillGap
82.45 / 76.26. SoftCeil stays REJECT. Not paid.

## Why this exists

v3.19 leftover hooks confirmed **H2 detect over-fire** (~56 detects vs
7–8 path HOs, ~8×). SoftCeil already showed the leftover is not the
0.85–0.90 cruise band. This cook **measures** those extra detects
before anyone fills a tighter gate.

v2.1 already rejected a blunt fusion-threshold raise (1.55 → 1.85)
on an older harness (gp 64.82 → 62.32). Do not retry that blindly.
`ep:loss_burst` stays ungated. Path HO is observe-only and is never
a live detect input.

## What changed

- Always-on endpoint-detect event log on `LeoAwareCCA` (t / reason / score / source)
- `on_loss` `ep:loss_burst` is logged too (that is most of leftover H2)
- `classify_detect_overfire` + `detect_overfire_hook` (dual-gate bars
  stay gp ≥ 75 / p95 ≤ 138.8)
- Shadow gates, all endpoint-legal and never drop `loss_burst`:
  `score_ge_1_85`, `score_ge_2_0`, `multi_reason`, `rtt_anchor`
- `python3 -m experiments.diag_v320_detect` on the FillGap lock path

No send-control lever. Constructor defaults stay False. Detect
threshold 1.65 and cooldown 0.42 stay untouched.

## Measured (5 seeds, 90s, FillGap + OpenSlot, SoftCeil off)

`python3 -m experiments.diag_v320_detect`  
Archive: `results/archive/20260906-v320-detect/`

| seed | FG gp | BBR gp | p95 | path HO | detect | on_loss | fusion | near HO | far HO |
|-----:|------:|-------:|----:|--------:|-------:|--------:|-------:|--------:|-------:|
| 13 | 96.80 | 97.31 | 72.21 | 7 | 56 | 53 | 3 | 11 | 45 |
| 7 | 75.36 | 75.08 | 67.81 | 8 | 56 | 51 | 5 | 15 | 41 |
| 42 | 81.25 | 81.25 | 97.56 | 7 | 56 | 50 | 6 | 14 | 42 |
| 99 | 73.19 | 72.98 | 64.09 | 7 | 56 | 50 | 6 | 13 | 43 |
| 123 | 85.61 | 85.57 | 79.65 | 8 | 57 | 54 | 3 | 12 | 45 |

Means: **gp 82.45 / p95 76.26** (FillGap lock reproduced). BBR 82.44 / 76.66.
Detect / path HO **7.63×**. Far-from-HO share **0.769**. HO recall **1.0**.

| Check | Bar | Result |
|-------|-----|--------|
| official gp | ≥ 75 | **82.45 PASS** |
| official p95 | ≤ 138.8 | **76.26 PASS** |
| beats FillGap lock | > 82.45 and p95 ≤ 76.26 | **NO** |

| Hypothesis | Verdict | Evidence |
|------------|---------|----------|
| **H4** most detects sit far from a real path HO | **CONFIRMED** | far frac 0.77 |
| **H5** a legal tighter gate keeps HO recall and cuts ≥ half of far | **WEAK** | score / multi / RTT-anchor cut **0** far fires |
| **H6** one primary owns half of far | **CONFIRMED** | far fires are `on_loss` `loss_burst` (258 vs fusion 23) |

Every fusion fire is **near** a path HO (`rtt_mad+ack_ia+loss_rtt`). The
~8× leftover is mobility-loss REPROBE, not a loose fusion threshold.

## Recommendation

Stay observe-only. Do **not**:

- cook a fusion-threshold raise (no-op on this over-fire; v2.1 already lost)
- gate `ep:loss_burst`
- retune detect cooldown
- retry a SoftCeil / 0.85–0.90 cruise fill
- bump Current

Next cook, if any, needs a **new mobility-loss taxonomy** (when is
`on_loss` a real hop vs cruise flicker) using endpoint signals only —
or leave detect alone.

## Official bars

| Check | Bar |
|-------|-----|
| gp mean | ≥ 75.0 |
| p95 mean | ≤ 138.8 |
| Current bump | must clearly beat FillGap 82.45 / 76.26 |

## Reproduce

```bash
python3 -m experiments.test_starlink_observability
python3 -m experiments.test_ope_integrity
python3 -m experiments.test_ascent_d_integrity
python3 -m experiments.diag_v320_detect
```

Replay hooks from the archived seed table (no resim):

```bash
python3 -m experiments.diag_v320_detect --replay
```

Current reproduce is still `python3 -m experiments.run_starlink --no-soft-ceil`.

Archive: `results/archive/20260906-v320-detect/`
