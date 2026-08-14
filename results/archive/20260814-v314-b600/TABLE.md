# leocc_v1 v3.14 B/600 follow-up — STOP (different bug)

**Decision: stop. Official gate still REJECT vs BBR (377.70 ≤ 379.80).**
FarHold default False. 80 ms floor not lowered. No second knob.
Not Current. Not paid. Do not merge.

B/600 is **not** the D/600 SER-lite / `ep:ack_ia+loss_burst` wipe
(`ser_lite=0`). Leftover 9.5 Mbps is 73% `congestive_recovery` on fade
overflow. A/1 already has that pattern and beats BBR — do not generalize
FarHold to fade-on-reconfig=0.

5-window CCA **unchanged** (no lever this follow-up):

| CCA | gp mean | p95 mean |
|-----|--------:|---------:|
| CUBIC | 31.14 | 87.20 |
| BBRv3approx | 379.80 | 89.60 |
| LeoAware Crest + FarHold | 377.70 | 89.60 |

| q | BBR gp/p95 | Crest+FarHold |
|---|-----------:|--------------:|
| A/1 | 408.33 / 36 | 409.44 / 36 |
| A/600 | 338.54 / 38 | 344.50 / 38 |
| B/600 | 400.60 / 64 | 391.11 / 64 |
| C/599 | 393.25 / 112 | 390.25 / 112 |
| D/600 | 358.29 / 198 | 353.18 / 198 |

Terr 78.62. D/600 kept. Integrity green.
Diagnosis: `docs/leoaware_v314_b600.md`.
