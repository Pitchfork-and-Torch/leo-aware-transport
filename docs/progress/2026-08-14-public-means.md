# Public progress note — 2026-08-14

**Audience:** orbitstack /progress (public-safe)  
**Harness:** `starlink_v1` product lock · endpoint-only · soft-QIR α=0.20  
**Scenario:** `leo_fast_ho` · seeds 13,7,42,99,123 · means only  
**Source archive:** `results/archive/20260812-v39-starlink-v1/`  
**Integrity:** `python3 -m experiments.test_ascent_d_integrity` — PASS (this run)

## Means vs BBR (no dish Mbps)

| CCA | Goodput mean (Mbps) | p95 RTT mean (ms) |
|-----|--------------------:|------------------:|
| CUBIC | 8.57 | 71.63 |
| BBRv3approx | 82.44 | 76.66 |
| **LeoAware (Crest)** | **82.07** | **76.26** |

LeoAware sits within ~0.5% goodput of BBR on the same OPE-fair path, with a slightly lower p95 mean. Absolute dual-gate numbers remain product-fenced; this note reports means only.

## Spot check (demo, single run)

| CCA | Goodput | p95 RTT |
|-----|--------:|--------:|
| CUBIC | 10.16 | 89.6 |
| BBRv3approx | 67.22 | 97.6 |
| LeoAware | 66.38 | 97.6 |

Demo is a shorter scenario than the multi-seed suite; use the table above for public means.

## Safety

- No VELA write operators enabled
- No failed-operator names
- No dish / PHY Mbps claims
- PATHHINT hybrid remains REJECT (v3.10); product path is endpoint Crest

## Reproduce

```bash
python3 -m experiments.test_ascent_d_integrity
python3 -m experiments.demo
# full means: python3 -m experiments.multi_seed --path-profile starlink_v1 --seeds 13,7,42,99,123
```
