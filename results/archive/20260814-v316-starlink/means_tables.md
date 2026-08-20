# v3.16 OpenSlot means — synthetic starlink_v1

Harness: `python3 -m experiments.run_starlink` (same as v3.9
`multi_seed` seeds 13,7,42,99,123 · 90s · endpoint-only · α=0.20).
**Synthetic** `starlink_v1`. Not dish PHY. No leocc / WetLinks / Zhao numbers.

OpenSlot archive opt-in: `True`. Committed `LeoAwareCCA()` default: **False**.

## leo_fast_ho means

| CCA | gp mean | p95 mean |
|-----|--------:|---------:|
| CUBIC | 8.57 | 71.63 |
| BBRv3approx | 82.44 | 76.66 |
| LeoAware v3.9 Crest (lock) | 82.07 | 76.26 |
| **LeoAware + OpenSlot** | **82.38** | **76.26** |

BBR lock reference: **82.44 / 76.66**.

## Per-seed LeoAware (leo_fast_ho)

| seed | gp | p95 |
|-----:|---:|----:|
| 13 | 96.69 | 72.21 |
| 7 | 75.34 | 67.81 |
| 42 | 81.15 | 97.56 |
| 99 | 73.12 | 64.09 |
| 123 | 85.61 | 79.65 |

## Other scenarios

| Scenario | LeoAware gp | p95 | note |
|----------|------------:|----:|------|
| leo_single | 83.51 | 74.95 | BBR 83.32 / 74.95 |
| terrestrial | 79.05 | 46.00 | bar ≥ 77 |

## Gates

| Check | Bar | Result |
|-------|-----|--------|
| gp mean clears BBR | > 82.44 | 82.38 FAIL |
| p95 mean vs BBR | ≤ 76.66 | 76.26 PASS |
| absolute gp | ≥ 75 | PASS |
| absolute p95 | ≤ 138.8 | PASS |
| terrestrial | ≥ 77 | 79.05 PASS |
| seeds | 13,7,42,99,123 | PASS |

**Decision: REJECT vs BBR.** Not Current. Not paid. Do not merge.
