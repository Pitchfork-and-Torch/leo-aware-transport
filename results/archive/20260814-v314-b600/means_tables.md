# leocc_v1 v3.14 B/600 follow-up — means (unchanged)

**STOP.** Different bug. Official FarHold table still REJECT vs BBR.

| CCA | gp mean | p95 mean |
|-----|--------:|---------:|
| CUBIC | 31.14 | 87.20 |
| BBRv3approx | 379.80 | 89.60 |
| LeoAware Crest + FarHold | 377.70 | 89.60 |

B/600 only: Crest 391.11 vs BBR 400.60. `ser_lite=0`. No `ack_ia+loss_burst`.
