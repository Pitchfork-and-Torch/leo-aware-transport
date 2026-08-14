# LeoAware v3.14 follow-up — B/600 diagnosis (stop)

**Date:** 2026-08-14  
**Branch:** `cursor/v314-d600-crest-b6ab`  
**Era:** `leocc_v1` (Lai et al., SIGCOMM 2025 / LeoCC). **Not Current. Not paid. Do not merge.**  
**Product lock:** synthetic `starlink_v1` / v3.9 Crest (82.07 / 76.26). Do not mix eras.

Cite: Lai, Zeqi et al. *LeoCC: Making Internet Congestion Control Robust to LEO
Satellite Dynamics*. ACM SIGCOMM 2025. DOI
[10.1145/3718958.3750491](https://doi.org/10.1145/3718958.3750491).
Capacity is **UDP iperf3 saturation**, not dish PHY / RF Mbps. p95 is **2×
ICMP OWD** on a separate Starlink SQM queue.

Official gate from the FarHold cook **stands**: Crest **377.70 ≤ 379.80** BBR.
FarHold stays **default False**. 80 ms floor **not** lowered.

## Ask

The leftover ~2.1 Mbps mean is mostly **B/600** (391.11 vs BBR 400.60).
FarHold did not fire (`min_rtt` ≈ 50 ms < 80 ms). Do **not** lower the
threshold to chase 2 Mbps.

If B/600 is the same SER-lite / `ep:ack_ia+loss_burst` wipe on `reconfig=0`
+ fade overflow → generalize FarHold to a fade-on-reconfig=0 hold (detect
still fires; never gate `ep:loss_burst`); A/1 and A/600 must stay unchanged.

If B/600 is a **different** bug → write that and **stop**. No second knob.

## Diagnose (B/600, same rails as D/600)

Script: `python -m experiments.diag_b600`. Archive:
`results/archive/20260814-v314-b600/diag/`.

### Path (no CCA)

| | |
|--|--|
| RTT (2×OWD) | min 46 / p50 **52** / p95 60 / max 82 ms |
| Slot-to-slot \|ΔRTT\| | p95 **10 ms**, max 34 ms |
| UDP-sat | min **16.56** / p50 425 / mean 408.26 / max 464 Mbps |
| `reconfig` | **0** (none invented) |
| classic_jump slots | 1 |
| rtt_mad-like slots | 4 |

Same *era* as D/600 (`reconfig=0`, deep UDP-sat cellar). **Not** the same
delay class: B is a mid-RTT window (p50 52 ms), not the 182 ms far-site tail.

### CCA internals (90 s, 1 MB, endpoint-only)

| Variant | gp | p95 | mean bw_est | rec | ser_lite | CA | ant |
|---------|---:|----:|------------:|----:|---------:|---:|----:|
| BBRv3approx | **400.60** | 64 | **423.5** | — | — | — | — |
| Crest (defaults) | 391.11 | 64 | 418.5 | 72 | **0** | 0 | 1 |
| Crest + `use_far_hold` | 391.11 | 64 | 418.3 | 72 | 0 | 0 | 1 |
| Crest no CA | 391.14 | 64 | 418.8 | 71 | 0 | 0 | 1 |
| Crest no LSG | 392.88 | 64 | 420.6 | 72 | 0 | 0 | 0 |
| Crest no anticipator | 391.35 | 64 | 419.3 | 71 | 0 | 0 | 0 |
| v3.7 OCE (Crest flags off) | 395.81 | 64 | 424.7 | 71 | 0 | 0 | 0 |

Crest REPROBE reasons on B/600 (72 in 90 s):

| reason | n | response |
|--------|--:|----------|
| `ep:loss_burst` | **40** | SER (cut 0.85) — **not** SER-lite |
| `ep:rtt_mad+loss_burst` | 26 | full invalidate (cut 0.58) |
| `ep:rtt_mad+loss_rtt` / `+ack_ia` | 6 | full invalidate |
| `ep:ack_ia+loss_burst` | **0** | — |

Mode histogram: Crest **1312 / 1800** slots `congestive_recovery` (73%).
BBR **1745 / 1800** `loss_ignored`. Crest mean cwnd 1870 mss vs BBR 4023 mss.
`bw_est` is **not** collapsed (418 vs 423).

### A/1 and A/600 (must stay unchanged)

| Window | gp vs BBR | rec | ser_lite | `ep:loss_burst` | `ack_ia+loss_burst` | cong_rec slots | CA |
|--------|-----------|----:|---------:|----------------:|--------------------:|---------------:|---:|
| A/1 | **409.44 > 408.33** | 73 | 0 | 28 | 0 | 964 (54%) | 52 |
| A/600 | **344.50 > 338.54** | 98 | 0 | 25 | 0 | 745 (41%) | 52 |
| B/600 | 391.11 < 400.60 | 72 | 0 | 40 | 0 | 1312 (73%) | 0 |

A already has fade overflow + `ep:loss_burst` SER and **beats** BBR. A
generalized “hold every `ep:loss_burst` on `reconfig=0`” would move A/1 and
A/600. That violates the follow-up constraint.

## Verdict — different bug. Stop.

| D/600 (FarHold target) | B/600 (this leftover) |
|------------------------|------------------------|
| SER-lite **92×** `ep:ack_ia+loss_burst` | **ser_lite = 0**; **zero** `ack_ia+loss_burst` |
| `bw_est` 267 vs BBR 384 | `bw_est` 418 vs BBR 423 (fine) |
| Anticipator 159 holds | Anticipator **1** hold |
| Congestive ~24% of slots | Congestive **73%** of slots |
| Gap **153 Mbps** | Gap **9.5 Mbps** |
| FarHold (min_rtt ≥ 80) recovered it to 353.18 | FarHold **does not arm** (min_rtt ≈ 50 ms) |

B/600 is **not** the SER-lite / `ep:ack_ia+loss_burst` wipe. The leftover is
Crest’s **0.72× congestive cut** on fade overflow (BBR ignores the same
marks) plus 26 full `rtt_mad+loss_burst` invalidates. That is a different
taxonomy.

**Do not** lower the 80 ms floor. **Do not** generalize FarHold to
fade-on-reconfig=0 (would retune A/1 and A/600). **Do not** invent a second
knob.

## 5-window table (unchanged)

No CCA change this follow-up. Official FarHold table still:

| CCA | gp mean | p95 mean |
|-----|--------:|---------:|
| CUBIC | 31.14 | 87.20 |
| BBRv3approx | **379.80** | **89.60** |
| LeoAware Crest + FarHold | **377.70** | **89.60** |

Terr 78.62. D/600 kept (353.18). Integrity green. Flag default False.

**REJECT vs BBR** (377.70 ≤ 379.80). p95 89.60 = 89.60. **Not Current. Not
paid. Do not merge.**

## Reproduce

```bash
python -m experiments.test_leocc_integrity
python -m experiments.test_ascent_d_integrity
python -m experiments.diag_b600 --tag 20260814-v314-b600 --workers 4
```
