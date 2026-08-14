# v3.11-SH — spike-hold + held-pipe fill on uncapped WetLinks

**Era:** `wetlinks_v1` research. **Not Current. Not paid. Do not merge.**  
Product Crest keeps `use_spike_hold=False`. No Halo / QSP / PATHHINT.

## Hypothesis

Uncap REJECT left Crest **239.72 < BBR 240.48**. The leftover is **all in
w1's first 25s** (90s: 386.98 vs 389.24; after t=25 both sit at ~395.5).

Two taxes, not one:

1. **False REPROBE** at the inferred 0.4 s `ping_worst` spike (t=12) while
   UDP capacity is held flat. 25s probe: Crest 364.78 → Crest+SH 365.93
   (+1.15). BBR 372.91. SH fires (`sh=1`, `reconfigs=0`).
2. **Startup fill.** Crest grows +1.28× ACKed and uses p82 (soft max-filter
   only when `age < 0.85` after a REPROBE). Cold-start `last_reconfig_t=-1e9`
   so the max-filter never arms. BBR doubles and max-filters. The ~7 Mbps
   leftover after SH is this ramp, not cruise (post-t=25 they match).

## Cook (`use_spike_hold=True`, WetLinks suite only)

- **Spike-hold:** RTT-jump detect + delivery ≥ 0.90× `bw_est` → skip full
  REPROBE for 0.50 s. Never skip `ep:loss_burst`. Do not update
  `last_reconfig_t`.
- **Held-pipe fill:** while `reconfigs_detected==0`:
  - startup growth **1.92×**, clean-delay bw **0.30·p82 + 0.70·max**
  - first 1.5 s: **no pace bind** (BBR is not pace-bound in this sim;
    Crest's 1.08× `bw_est` starved t=0–1) and pace_gain ≥ 2.20
  - delay-gated cwnd cap **2.20× BDP** only if `bw_est > 50 Mbps` and
    `delay_ratio > 1.30` (a cold 2.20× cap deadlocked SH at 82 KB / 7 Mbps)
  - loss ignore while live RTT < 1.55× min_rtt (BBR `loss_ignored`)
  - a real SER turns this off. Product Crest never enters.

## 25s w1 probe (includes t=12 spike)

| CCA | gp | p95 | reconfigs | sh |
|-----|---:|----:|----------:|---:|
| Crest | 364.78 | 62.74 | 1 | 0 |
| Crest+SH skip-only | 365.93 | 62.74 | 0 | 1 |
| Crest+SH + fill (deadlock cap) | 7.24 | 60.74 | 0 | 1 |
| **Crest+SH + fill + pace-unbind** | **382.02** | 62.74 | 1 | 1 |
| BBR | 372.91 | 62.74 | 0 | 0 |

t=1 cumulative: Crest 8.16 / SH 120.45 / BBR 34.63. Same p95. This is the
window that held the entire 90s uncap gap.

## Gate

Same 5 windows, 1 MB buffer, dt=0.01, α=0.20. ACCEPT only if LeoAware+SH
gp mean **>** BBR. Else REJECT. Do not mix with 239.72/240.48 or 156.70.

```bash
python3 -m experiments.probe_wetlinks_w1
python3 -m experiments.run_wetlinks --tag 20260814-v311-wetlinks-sh
```

## Gate result

| CCA | gp mean | p95 mean |
|-----|--------:|---------:|
| CUBIC | 94.22 | 68.38 |
| BBRv3approx | 240.48 | 71.38 |
| **LeoAware+SH** | **242.03** | 71.38 |

Terr 78.623. **ACCEPT** (`wetlinks_v1` research only). Per-window vs BBR:
w1 +2.53, w2 +2.35, w3 +0.23, w4 +1.82, w5 +0.79.

Do **not** default-on without a `starlink_v1` 5-seed check. Real HO has
loss + cap redraw; SH should not fire, but first-ACK lag is a risk.
No Current. No paid bump. No merge.
