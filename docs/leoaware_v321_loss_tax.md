# LeoAware v3.21 — on_loss / ep:loss_burst taxonomy

**Date:** 2026-09-07  
**Branch:** `cursor/loss-burst-taxonomy-1a2f`  
**Era:** synthetic `starlink_v1`  
**Lever:** none (observe + taxonomy shadows)  
**Decision:** pending 5-seed measure. Current stays v3.17 FillGap
82.45 / 76.26. SoftCeil stays REJECT. Not paid.

## Why this exists

PR #27 / v3.20 measured leftover H2: fusion is clean; the ~8× over-fire
is `on_loss` `ep:loss_burst`. Legal fusion shadows cut **0** far fires.
This cook measures a **mobility-loss taxonomy** — when is `on_loss` a
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

## Hypotheses

| Hypothesis | Meaning |
|------------|---------|
| **H7** | Far `on_loss` is the 1.4s pacemaker / cluster-2 cruise |
| **H8** | A legal taxonomy keeps HO recall and cuts ≥ half of far |
| **H9** | Some path HOs are covered only by `on_loss` (fusion miss) |

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
