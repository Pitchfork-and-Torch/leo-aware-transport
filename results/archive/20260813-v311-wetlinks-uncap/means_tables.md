# v3.11 WetLinks uncap — 1 MB buffer (REJECT)

Same five windows. **This table is the gate.** Do not mix with capped
250 KB (Crest 156.70/63.98), `starlink_v1` 82.09/76.26, or `ope_v36` 58/152.

| | buffer | send ceiling at dt=0.01 |
|--|-------:|------------------------:|
| capped footnote | 250 KB | 200 Mbps |
| **this cook** | **1 MB** | **800 Mbps** |

Capacity is UDP iperf download mean, hold-expanded. Not dish PHY.

## Geometry (unchanged)

oracle gp mean **244.85** / path p95 mean **60.78**. PASS.

## Uncapped 5-window CCA (endpoint, α=0.20, dt=0.01, 1 MB)

| window | oracle | Leo gp | BBR gp | CUBIC gp | Leo p95 | BBR p95 |
|--------|-------:|-------:|-------:|---------:|--------:|--------:|
| w1 | 396.17 | 386.98 | 389.24 | 209.03 | 62.74 | 62.74 |
| w2 | 405.07 | 396.97 | 396.84 | 3.52 | 56.10 | 56.10 |
| w3 | 66.02 | 64.29 | 64.72 | 64.94 | 92.24 | 93.24 |
| w4 | 193.42 | 188.86 | 189.88 | 190.09 | 70.86 | 74.86 |
| w5 | 163.58 | 161.50 | 161.73 | 3.52 | 69.95 | 69.95 |
| **mean** | **244.85** | **239.72** | **240.48** | 94.22 | **70.38** | 71.38 |

Terr (synthetic, product 250 KB): LeoAware **78.623** @ 46 ms.

| Gate | | |
|------|--|--|
| Crest gp > BBR | 239.72 < 240.48 | **FAIL — kill** |
| gp ≥ 75 | 239.72 | PASS |
| p95 ≤ 138.8 | 70.38 | PASS |
| terr ≥ 77 | 78.62 | PASS |

**Decision: REJECT.** Crest does not clear BBR at the uncapped ceiling.
Uncap itself worked: w1/w2 now ~387–397 Mbps (were ~190 at 250 KB). Both
CCAs are ~98% of oracle. Crest p95 is 1 ms better; that is not a gp win.
CUBIC dies on 0.4% ping-loss windows (w2, w5). w3 p95 ~92 ms is the 1 MB
queue on a 66 Mbps cycle (sojourn tax), not a Crest invention.

No Current. No paid bump. No merge. Product lock stays synthetic
`starlink_v1` / v3.9 Crest.
