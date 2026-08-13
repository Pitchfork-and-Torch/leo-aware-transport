# v3.11 WetLinks (`wetlinks_v1`) — geometry

Hold-expanded slices. See `traces/wetlinks/MANIFEST.md`.

| window | oracle gp Mbps | path p95 ms | path max ms |
|--------|---------------:|------------:|------------:|
| w1 Enschede 2023-11-10 | 396.17 | 58.73 | 84.29 |
| w2 Enschede 2024-02-15 | 405.07 | 52.10 | 105.08 |
| w3 Osnabrück 2023-09-30 | 66.02 | 68.24 | 94.14 |
| w4 Osnabrück 2023-12-20 | 193.42 | 64.86 | 109.87 |
| w5 Osnabrück 2024-02-23 | 163.58 | 59.95 | 83.79 |
| **mean** | **244.85** | **60.78** | — |

Geometry dual-gate: **PASS** (mean gp≥75 and p95≤138.8).

CCA means (Crest / BBR / CUBIC + terr) are filled after
`python3 -m experiments.run_wetlinks --tag 20260813-v311-wetlinks`.
