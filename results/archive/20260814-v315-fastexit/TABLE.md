# leocc_v1 scorecard (v3.15 LeanCatch; FastExit died)

Decision: **REJECT**. LeanCatch gp mean 358.94 ≤ BBR lock 379.80. Not Current. No paid. Do not merge.

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
| **LeoAware LeanCatch** | **358.94** | **89.60** |
| LeoAware Crest (flags off) | 337.97 | 89.60 |
| FarHold-on (PR #18 cite) | 377.70 | 89.60 |

Terrestrial LeoAware 78.62 @ 46.0 ms (product defaults, flag off).

The gate is the **mean**. D/600 is not dropped. A/1 and A/600 must not drop vs 409.44 / 344.50.
