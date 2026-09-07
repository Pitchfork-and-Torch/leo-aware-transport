# LeoAware v3.21 — on_loss / ep:loss_burst taxonomy

**Date:** 2026-09-07  
**Branch:** `cursor/loss-burst-taxonomy-1a2f`  
**Era:** synthetic `starlink_v1`  
**Lever:** none (observe + taxonomy shadows)  
**Decision:** **REJECT a live loss-burst gate.** Current stays v3.17 FillGap
82.45 / 76.26. SoftCeil stays REJECT. Not paid.

## Why this exists

v3.20 measured leftover H2: fusion is clean; the ~8x over-fire
is `on_loss` `ep:loss_burst`. Legal fusion shadows cut **0** far fires.
This cook measured a **mobility-loss taxonomy** — when is `on_loss` a
real hop vs cruise flicker — using endpoint signals only.

Path HO stays fail-closed (never a live detect input). SoftCeil default
stays **False**. FillGap / OpenSlot constructor defaults stay **False**.
Do not bump Current without beating FillGap 82.45 / 76.26.

## What changed

- Detect events carry `cluster_n`, `rtt_ratio`, `dt_last_detect`
- Quiet-window 2-loss clusters are logged as suppressed candidates
- `classify_loss_taxonomy` + `loss_taxonomy_hook` (dual-gate bars stay
  gp ≥ 75 / p95 ≤ 138.8)
- Taxonomy shadows **may** classify `loss_burst` (that is the leftover):
  `cluster_ge_3`, `cluster_ge_4`, `first_after_3s`, `first_after_5s`,
  `rtt_ge_1_12`. Fusion stays kept.
- `python3 -m experiments.diag_v321_loss_tax` on the FillGap lock path

No send-control lever. Detect threshold 1.65 and cooldown 0.42 stay
untouched.

## Measured (5 seeds, 90s, FillGap + OpenSlot, SoftCeil off)

`python3 -m experiments.diag_v321_loss_tax`  
Archive: `results/archive/20260907-v321-loss-tax/`

| seed | FG gp | BBR gp | p95 | path HO | on_loss-only HO | far on_loss | far cluster2 | far pace |
|-----:|------:|-------:|----:|--------:|----------------:|------------:|-------------:|---------:|
| 13 | 96.80 | 97.31 | 72.21 | 7 | 4 | 45 | 3 | 37 |
| 7 | 75.36 | 75.08 | 67.81 | 8 | 3 | 41 | 4 | 30 |
| 42 | 81.25 | 81.25 | 97.56 | 7 | 1 | 42 | 12 | 31 |
| 99 | 73.19 | 72.98 | 64.09 | 7 | 1 | 43 | 5 | 33 |
| 123 | 85.61 | 85.57 | 79.65 | 8 | 5 | 45 | 4 | 40 |

Means: **gp 82.45 / p95 76.26** (FillGap lock reproduced). BBR 82.44 / 76.66.
Far on_loss **216**. Pacemaker (dt 1.4–1.8s) **171**. Cluster-2 only **28**.
On_loss-only path HOs **14**. Fusion-covered HOs **23**.

| Check | Bar | Result |
|-------|-----|--------|
| official gp | ≥ 75 | **82.45 PASS** |
| official p95 | ≤ 138.8 | **76.26 PASS** |
| beats FillGap lock | > 82.45 and p95 ≤ 76.26 | **NO** |

| Hypothesis | Verdict | Evidence |
|------------|---------|----------|
| **H7** far on_loss is the 1.4s pacemaker | **CONFIRMED** | 171/216 far fires sit on the 1.4–1.8s gap |
| **H8** a legal taxonomy keeps HO recall and cuts ≥ half of far | **RECKLESS** | `first_after_*` / `rtt_ge_1_12` cut far and drop HO recall. `cluster_ge_3` cuts 28 far and is reckless on seeds 99/123 |
| **H9** some path HOs are on_loss-only | **CONFIRMED** | 14 HOs have no fusion fire; covering `on_loss` looks like the pacemaker (dt ~1.4, rtt_ratio ~1.0) |

Hop-covering `on_loss` is not a different endpoint class. The leftover
pacemaker **is** the hop detector for fusion-missed HOs.

## Recommendation

**REJECT a live `ep:loss_burst` gate.** Leave detect alone on this
synthetic harness. Do **not**:

- cook a cluster-floor / first-after / RTT-ratio loss-burst gate
- cook a fusion-threshold raise (v3.20 already no-op)
- retune detect cooldown
- retry SoftCeil / 0.85–0.90 cruise fill
- bump Current

Next cook, if any, needs a named public ≥90s UDP-sat+delay source — not
another detect taxonomy on `starlink_v1`.

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
python3 -m experiments.diag_v321_loss_tax
```

Replay hooks from the archived seed table (no resim):

```bash
python3 -m experiments.diag_v321_loss_tax --replay
```

Current reproduce is still `python3 -m experiments.run_starlink --no-soft-ceil`.

Archive: `results/archive/20260907-v321-loss-tax/`
