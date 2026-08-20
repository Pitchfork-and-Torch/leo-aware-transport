# Public progress note — 2026-08-20

**Audience:** orbitstack /progress (public-safe)  
**Harness:** `starlink_v1` product lock · endpoint-only · soft-QIR α=0.20  
**Scenario:** `leo_fast_ho` · seeds 13,7,42,99,123 · means only  
**Source archive:** `results/archive/20260814-v317-fillgap/` (PR #22)  
**Integrity:** constructor defaults `use_fill_gap=False` / `use_openslot=False`

## Current product dual-gate lock

| CCA | Goodput mean (Mbps) | p95 RTT mean (ms) |
|-----|--------------------:|------------------:|
| CUBIC | 8.57 | 71.63 |
| BBRv3approx | 82.44 | 76.66 |
| **LeoAware v3.17 FillGap** | **82.45** | **76.26** |
| LeoAware v3.9 Crest (prior lock) | 82.07 | 76.26 |

Beats Crest on gp, matches p95, edges BBR. Absolute bars PASS (gp ≥ 75, p95 ≤ 138.8). Terr 79.05 ≥ 77. No dish / PHY Mbps.

Reproduce Current: `python3 -m experiments.run_starlink`.

## Safety

- No VELA write operators enabled
- No failed-operator names
- No dish / PHY Mbps claims
- `ope_v36`, WetLinks, `zhao_zenodo23`, and `leocc_v1` remain research-only
- PATHHINT hybrid remains REJECT (v3.10)

## Reproduce

```bash
python3 -m experiments.test_ascent_d_integrity
python3 -m experiments.test_ope_integrity
python3 -m experiments.run_starlink
```
