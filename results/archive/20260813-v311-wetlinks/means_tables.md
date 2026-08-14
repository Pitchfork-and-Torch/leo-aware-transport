# v3.11 WetLinks (`wetlinks_v1`)

Hold-expanded slices. See `traces/wetlinks/MANIFEST.md`.
Replay slot: product `dt=0.01` (CSV samples are 50 ms; path holds).
250 KB buffer send ceiling ≈ **200 Mbps** (`8 * buffer / dt`).

## Geometry (no CCA)

| window | oracle gp Mbps | path p95 ms | path max ms |
|--------|---------------:|------------:|------------:|
| w1 Enschede 2023-11-10 | 396.17 | 58.73 | 84.29 |
| w2 Enschede 2024-02-15 | 405.07 | 52.10 | 105.08 |
| w3 Osnabrück 2023-09-30 | 66.02 | 68.24 | 94.14 |
| w4 Osnabrück 2023-12-20 | 193.42 | 64.86 | 109.87 |
| w5 Osnabrück 2024-02-23 | 163.58 | 59.95 | 83.79 |
| **mean** | **244.85** | **60.78** | — |

Geometry dual-gate: **PASS**.

## 5-window CCA (endpoint Crest / BBR / CUBIC)

| window | Leo gp | BBR gp | CUBIC gp | Leo p95 | BBR p95 |
|--------|-------:|-------:|---------:|--------:|--------:|
| w1 | 189.93 | 197.19 | 29.58 | 60.74 | 60.74 |
| w2 | 189.98 | 196.00 | 3.52 | 54.10 | 54.10 |
| w3 | 64.24 | 64.72 | 62.34 | 74.24 | 76.24 |
| w4 | 180.00 | 189.89 | 93.32 | 66.86 | 66.86 |
| w5 | 159.35 | 161.75 | 3.52 | 63.95 | 63.95 |
| **mean** | **156.70** | **161.91** | 38.46 | **63.98** | 64.38 |

Terr (synthetic, seeds 13,7,42,99,123): LeoAware **78.623** @ 46 ms.

| Gate | Value | Bar | |
|------|------:|----:|--|
| gp mean | 156.70 | ≥ 75 | PASS |
| p95 mean | 63.98 | ≤ 138.8 | PASS |
| terr gp | 78.62 | ≥ 77 | PASS |

**Decision: ACCEPT `wetlinks_v1` era only.** Not Current. No paid bump.
Do not mix with `starlink_v1` 82.09/76.26 or `ope_v36` 58/152.
Product CCA on synthetic `starlink_v1` remains v3.9 Crest.

w1/w2 sit at ~190 Mbps because of the 200 Mbps buffer/dt ceiling, not
because the dish is 190 Mbps. w3 Leo 64.24 is below 75 (oracle 66.02);
the gate is the five-window mean. CUBIC dies on the 0.4% ping-loss
windows (w2, w5). BBR is slightly ahead of Crest on gp (same pattern as
synthetic `starlink_v1`).
