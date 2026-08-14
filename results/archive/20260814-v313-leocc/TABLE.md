# leocc_v1 scorecard (v3.13)

Decision: **ACCEPT_ERA_REJECT_BBR**. absolute 75/138.8 PASS on leocc_v1 means; Crest does not clear BBR. Not Current. No paid. Do not merge.

Oracle UDP-sat mean **394.95** Mbps → **PASS** (bar ≥ 75).
Native 2×OWD p95 mean **85.20** ms → **PASS** (bar ≤ 138.8).
Native OWD p95 mean 42.60 ms (diagnostic).

Capacity is UDP saturation, not dish PHY. RTT = 2 × LeoReplayer OWD.
Not Current. Do not merge. Do not mix with wetlinks_v1 / zhao / starlink_v1 Crest.

| q | site | trace | native UDP-sat oracle | OWD p95 | 2×OWD p95 | resampled oracle | resampled path p95 |
|---|------|------:|----------------------:|--------:|----------:|-----------------:|-------------------:|
| q00 | A | 1 | 425.83 | 16.00 | 32.00 | 425.79 | 32.00 |
| q25 | A | 600 | 353.33 | 16.00 | 32.00 | 353.34 | 34.00 |
| q50 | B | 600 | 408.26 | 30.00 | 60.00 | 408.30 | 60.00 |
| q75 | C | 599 | 406.40 | 54.00 | 108.00 | 406.17 | 108.00 |
| q100 | D | 600 | 380.91 | 97.00 | 194.00 | 380.98 | 194.00 |
| **mean** | | | **394.95** | **42.60** | **85.20** | **394.92** | **85.60** |

### CCA means (5 downlink windows, dt=0.01, 1 MB buffer)

| CCA | gp mean | p95 mean |
|-----|--------:|---------:|
| CUBIC | 31.14 | 87.20 |
| BBRv3approx | 379.80 | 89.60 |
| **LeoAware Crest** | **337.97** | **89.60** |

Terrestrial LeoAware 78.62 @ 46.0 ms.

### Per-window CCA (gate is the mean, not these rows)

| q | CUBIC gp/p95 | BBR gp/p95 | Crest gp/p95 |
|---|-------------:|-----------:|-------------:|
| q00 A/1 | 49.88 / 34 | 408.33 / 36 | 409.44 / 36 |
| q25 A/600 | 51.61 / 34 | 338.54 / 38 | 344.50 / 38 |
| q50 B/600 | 29.56 / 62 | 400.60 / 64 | 391.11 / 64 |
| q75 C/599 | 16.28 / 110 | 393.25 / 112 | 340.20 / 112 |
| q100 D/600 | 8.38 / 196 | 358.29 / 198 | 204.61 / 198 |

Crest does not Pareto-improve BBR. D/600 is a real far-site tail — not dropped.
