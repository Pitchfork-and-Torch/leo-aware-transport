# leocc_v1 v3.15 LeanCatch means

Decision: **REJECT**.

Era `leocc_v1` (Lai et al., SIGCOMM 2025). Capacity = UDP iperf3 sat, not dish PHY. p95 = 2× ICMP OWD. Do not mix with starlink_v1 82.07/76.26.

| CCA | gp mean | p95 mean |
|-----|--------:|---------:|
| CUBIC | 31.14 | 87.20 |
| BBRv3approx | 379.80 | 89.60 |
| LeoAware Crest (flags off) | 337.97 | 89.60 |
| FarHold-on (PR #18 cite) | 377.70 | 89.60 |
| **LeoAware LeanCatch** | **358.94** | **89.60** |

Terr (product Crest, 250 KB, seeds 13,7,42,99,123): 78.62 @ 46.0 ms.

### Per-window (gate is the mean; D/600 kept)

| q | CUBIC | BBR | Crest off | LeanCatch |
|---|------:|----:|----------:|----------:|
| q00 q00_A_downlink_001 | 49.88 / 34 | 408.33 / 36 | 409.44 / 36 | 409.65 / 36 |
| q25 q25_A_downlink_600 | 51.61 / 34 | 338.54 / 38 | 344.50 / 38 | 344.68 / 38 |
| q50 q50_B_downlink_600 | 29.56 / 62 | 400.60 / 64 | 391.11 / 64 | 392.32 / 64 |
| q75 q75_C_downlink_599 | 16.28 / 110 | 393.25 / 112 | 340.20 / 112 | 363.61 / 112 |
| q100 q100_D_downlink_600 | 8.38 / 196 | 358.29 / 198 | 204.61 / 198 | 284.43 / 198 |
