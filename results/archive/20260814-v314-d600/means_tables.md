# leocc_v1 v3.14 FarHold — means table

**Decision: ACCEPT_ERA_REJECT_BBR / REJECT vs BBR.**
Crest gp mean 377.70 ≤ BBR 379.80. p95 89.60 = 89.60.
Not Current. Not paid. Do not merge. Do not mix eras.

Capacity is UDP iperf3 saturation, not dish PHY. p95 is 2× ICMP OWD
(separate Starlink queue). Soft-QIR α=0.20. Era buffer 1 MB.
FarHold opted in on LeoCC windows; product Crest default stays off.

## CCA means (5 downlink windows)

| CCA | gp mean | p95 mean |
|-----|--------:|---------:|
| CUBIC | 31.14 | 87.20 |
| BBRv3approx | 379.80 | 89.60 |
| LeoAware Crest + FarHold | 377.70 | 89.60 |

Terrestrial LeoAware 78.62 @ 46.0 ms (product 250 KB, seeds 13,7,42,99,123).

## Per-window (gate is the mean)

| q | site/trace | CUBIC gp/p95 | BBR gp/p95 | Crest+FarHold gp/p95 |
|---|------------|-------------:|-----------:|---------------------:|
| q00 | A/1 | 49.88 / 34 | 408.33 / 36 | 409.44 / 36 |
| q25 | A/600 | 51.61 / 34 | 338.54 / 38 | 344.50 / 38 |
| q50 | B/600 | 29.56 / 62 | 400.60 / 64 | 391.11 / 64 |
| q75 | C/599 | 16.28 / 110 | 393.25 / 112 | 390.25 / 112 |
| q100 | D/600 | 8.38 / 196 | 358.29 / 198 | 353.18 / 198 |

v3.13 Crest (no FarHold): 337.97 mean; D/600 204.61; C/599 340.20.
Do not advertise A/1 as a BBR win. Do not drop D/600.
