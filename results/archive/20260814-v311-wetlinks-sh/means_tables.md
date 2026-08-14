# v3.11-SH WetLinks uncap + spike-hold + held-pipe fill (ACCEPT)

Same five windows, 1 MB, dt=0.01, α=0.20. **This table is the gate.**
Do not mix with uncap Crest 239.72/240.48, capped 156.70/63.98,
`starlink_v1` 82.09/76.26, or `ope_v36` 58/152.

| | buffer | send ceiling at dt=0.01 |
|--|-------:|------------------------:|
| capped footnote | 250 KB | 200 Mbps |
| uncap REJECT | 1 MB | 800 Mbps |
| **this cook** | **1 MB** | **800 Mbps** |

Capacity is UDP iperf download mean, hold-expanded. Not dish PHY.
Product Crest keeps `use_spike_hold=False`. No Halo / QSP / PATHHINT.

## Geometry (unchanged)

oracle gp mean **244.85** / path p95 mean **60.78**. PASS.

## Uncapped 5-window CCA (LeoAware+SH vs BBR, 1 MB)

| window | oracle | Leo+SH gp | BBR gp | CUBIC gp | Leo p95 | BBR p95 | sh | rec |
|--------|-------:|----------:|-------:|---------:|--------:|--------:|---:|----:|
| w1 | 396.17 | 391.77 | 389.24 | 209.03 | 62.74 | 62.74 | 1 | 1 |
| w2 | 405.07 | 399.19 | 396.84 | 3.52 | 56.10 | 56.10 | 1 | 64 |
| w3 | 66.02 | 64.95 | 64.72 | 64.94 | 93.24 | 93.24 | 1 | 1 |
| w4 | 193.42 | 191.70 | 189.88 | 190.09 | 74.86 | 74.86 | 1 | 0 |
| w5 | 163.58 | 162.52 | 161.73 | 3.52 | 69.95 | 69.95 | 0 | 64 |
| **mean** | **244.85** | **242.03** | **240.48** | 94.22 | **71.38** | 71.38 |

Terr (synthetic, product 250 KB): LeoAware **78.623** @ 46 ms.

| Gate | | |
|------|--|--|
| Leo+SH gp > BBR | 242.03 > 240.48 | **PASS** |
| gp ≥ 75 | 242.03 | PASS |
| p95 ≤ 138.8 | 71.38 | PASS |
| terr ≥ 77 | 78.62 | PASS |

**Decision: ACCEPT** (`wetlinks_v1` research era only).

Per-window Leo+SH minus BBR: w1 +2.53, w2 +2.35, w3 +0.23, w4 +1.82,
w5 +0.79. w2/w5 `reconfigs_detected=64` are `ep:loss_burst` SER on the
0.4% ping-loss windows (CUBIC dies there); SH never gates that path.
p95 matches BBR (uncap Crest had a 1 ms mean edge — given back).

No Current. No paid bump. No merge. Do **not** default-on SH without a
`starlink_v1` 5-seed check. Product lock stays synthetic `starlink_v1` /
v3.9 Crest.
