# v3.18 SoftCeil means — synthetic starlink_v1

Harness: `python3 -m experiments.run_starlink` (same as v3.9
`multi_seed` seeds 13,7,42,99,123 · 90s · endpoint-only · α=0.20).
**Synthetic** `starlink_v1`. Not dish PHY. No leocc / WetLinks / Zhao numbers.

SoftCeil archive opt-in: `True`. FillGap archive opt-in: `True`
(0.85 not retuned). OpenSlot archive opt-in: `True` (0.80 not retuned).
Committed `LeoAwareCCA()` defaults: **False**.

## leo_fast_ho means

| CCA | gp mean | p95 mean |
|-----|--------:|---------:|
| CUBIC | 8.57 | 71.63 |
| BBRv3approx | 82.44 | 76.66 |
| LeoAware v3.9 Crest (prior lock) | 82.07 | 76.26 |
| LeoAware + OpenSlot (v3.16) | 82.38 | 76.26 |
| LeoAware + FillGap (Current) | 82.45 | 76.26 |
| **LeoAware + SoftCeil** | **82.35** | **76.26** |

BBR lock reference: **82.44 / 76.66**.
FillGap Current: **82.45 / 76.26**.

## Per-seed LeoAware (leo_fast_ho)

| seed | gp | p95 |
|-----:|---:|----:|
| 13 | 96.31 | 72.21 |
| 7 | 75.36 | 67.81 |
| 42 | 81.26 | 97.56 |
| 99 | 73.19 | 64.09 |
| 123 | 85.62 | 79.65 |

Seed 13 floor: Crest 96.65 / OpenSlot 96.69 / FillGap 96.80 → 96.31.

## Other scenarios

| Scenario | LeoAware gp | p95 | note |
|----------|------------:|----:|------|
| leo_single | 83.56 | 74.95 | BBR 83.32 / 74.95 |
| terrestrial | 79.05 | 46.00 | bar ≥ 77 |

## Gates

| Check | Bar | Result |
|-------|-----|--------|
| gp mean clears BBR | > 82.44 | 82.35 FAIL |
| p95 mean vs BBR | ≤ 76.66 | 76.26 PASS |
| seed 13 vs Crest lock | ≥ 96.65 | 96.31 FAIL |
| seed 13 vs OpenSlot | ≥ 96.69 | 96.31 FAIL |
| seed 13 vs FillGap | ≥ 96.80 | 96.31 FAIL |
| p95 vs FillGap Current | ≤ 76.26 | 76.26 PASS |
| absolute gp | ≥ 75 | PASS |
| absolute p95 | ≤ 138.8 | PASS |
| terrestrial | ≥ 77 | 79.05 PASS |
| seeds | 13,7,42,99,123 | PASS |

**Decision: REJECT vs BBR.** Research-on-product-era. Current stays v3.17 FillGap unless the margin clearly widens. Not paid.
