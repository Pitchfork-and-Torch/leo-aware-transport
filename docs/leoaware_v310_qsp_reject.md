# LeoAware v3.10-QSP — Queue-Sojourn Pacing — REJECT

**Date:** 2026-08-13  
**Branch:** `cursor/v310-halo-84b8`  
**Decision:** **REJECT.** This cook left product CCA on Crest.  
**Current is now v3.17 FillGap.** This cook is not Current.

## Bet (one cook; Halo/Pulse/EpochMemory not revived)

**Queue-sojourn pacing.** Soft-QIR α stays **frozen 0.20**. Invert the
*visible* ACK excess (`rtt − min_rtt`, which already includes
`min(25ms, 0.20×sojourn)`) and discount `pace_gain` only. Tighten send
burst from 1.5× to 1.15× when excess > 8 ms. **Never raise cruise BDP.**

`use_qsp` default **False** (Crest). Evaluated ON for this scorecard.

## Options not taken

| Option | Why not this cook |
|--------|-------------------|
| SkyPulse PATHHINT | Assist path; would not move the endpoint product table. |
| Seed-99 gp hole | Seed 99 is 72.83 vs oracle **74.63** (~97.6% — same utilization as the mean). Geometry, not a reclaim miss. No seed-id branching. |
| Real Starlink CSV | In-repo CSVs are **synthetic** (`traces/starlink_v1_seed13.csv`, etc.). No public dish trace. Skipped. |
| Halo / Pulse / EpochMemory | Already honest REJECT. Not revived. |

## Scorecard (90s `leo_fast_ho`, seeds 13,7,42,99,123, `starlink_v1`)

| CCA | gp mean | p95 mean | vs Crest |
|-----|--------:|---------:|----------|
| Crest (defaults) | **82.089** | **76.264** | baseline |
| **QSP on** | **82.047** | **76.264** | gp −0.042; p95 flat |
| BBRv3approx | 82.439 | 76.664 | research only |

Per-seed QSP gp: 13→96.65 · 7→74.89 · 42→80.67 · 99→72.72 · 123→85.30  
Per-seed QSP p95: identical to Crest (72.21 / 67.81 / 97.56 / 64.09 / 79.65).

Terrestrial QSP **78.623 / 46.0** (same as Crest; ≥77 PASS).

## Gates

| Check | Bar | Result |
|-------|-----|--------|
| gp mean | ≥ 75 | **82.047 PASS** |
| p95 mean | ≤ 138.8 | **76.264 PASS** |
| terr gp | ≥ 77 | **78.623 PASS** |
| integrity | green | **PASS** |
| Pareto vs Crest 82.09/76.26 | gp↑ w/o p95↑ **or** p95↓ w/o gp↓ | **FAIL** (gp down, p95 unchanged) |

p95 is path-dominated (path-base mean 70.79 + frozen QIR excess). Pace
discounts do not change the ACK p95 mix on this orbit.

**Decision: REJECT.** `use_qsp=False`. Crest stays default.

Archive: `results/archive/20260813-v310-qsp/`
