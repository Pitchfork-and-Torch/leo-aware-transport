# LeoAware v3.14 — D/600 far-site diagnosis + FarHold (research era)

**Date:** 2026-08-14  
**Branch:** `cursor/v314-d600-crest-b6ab`  
**Era:** `leocc_v1` (Lai et al., SIGCOMM 2025 / LeoCC). **Not Current. Not paid. Do not merge.**  
**Product lock:** synthetic `starlink_v1` / v3.9 Crest (82.07 / 76.26). Do not mix eras.

Cite: Lai, Zeqi et al. *LeoCC: Making Internet Congestion Control Robust to LEO
Satellite Dynamics*. ACM SIGCOMM 2025. DOI
[10.1145/3718958.3750491](https://doi.org/10.1145/3718958.3750491).
Traces: Tsinghua Cloud `4.8K.zip` (not vendored). Capacity is **UDP iperf3
saturation**, not dish PHY / RF Mbps. p95 is **2× ICMP OWD** on a separate
Starlink SQM queue.

## Problem (v3.13 leftover)

Five catalog-quantile downlink 90 s windows, `dt=0.01`, era buffer 1 MB,
endpoint Crest defaults, Soft-QIR α=0.20:

| CCA | gp mean | p95 mean |
|-----|--------:|---------:|
| CUBIC | 31.14 | 87.20 |
| BBRv3approx | **379.80** | **89.60** |
| LeoAware Crest | **337.97** | **89.60** |

The mean gap is almost entirely **D/600** (q100, far-site): Crest **204.61** vs
BBR **358.29** vs oracle UDP-sat **380.91**. Path 2×OWD p95 = 194 ms. D/600 is
**not** dropped. A/1 and A/600 Crest is slightly *ahead* of BBR. B/C/D behind.
p95 is path-dominated — do not market it as CCA delay control.

## Diagnose first (D/600 only)

Script: `python -m experiments.diag_d600`. Archive:
`results/archive/20260814-v314-d600/diag/`.

### Path (no CCA)

| | |
|--|--|
| RTT (2×OWD) | min 148 / p50 182 / p95 194 / max 220 ms |
| Slot-to-slot \|ΔRTT\| | p95 **10 ms**, max 48 ms |
| UDP-sat | min **22.8** / p50 382 / p82 440 / mean 380.91 / max 496 Mbps |
| `reconfig` | **0** (none invented) |
| classic_jump slots (`rtt > 1.55×med` and Δ>12 ms) | **0** |
| rtt_mad-like slots (z>3.5 and Δ>10 ms) | **4** |
| fraction RTT > 1.35× p50 | **0** (Crest Abort cannot fire on path median) |
| fraction RTT > 1.18× min | **0.81** (if min_rtt locks on 148 ms, LSG/delay look “inflated”) |

This is a **high-OWD, low-jitter, deep-fade** window. Capacity flickers into
the 20 Mbps cellar; delay does not jump like a handover.

### CCA internals (same 90 s, 1 MB, endpoint-only)

| Variant | gp | p95 | mean bw_est | mean cwnd | reprobes | CA | LSG clamps | ant holds |
|---------|---:|----:|------------:|----------:|---------:|---:|-----------:|----------:|
| BBRv3approx | **358.29** | 198 | **384.5** | 11794 mss | — | — | — | — |
| Crest (defaults) | 204.61 | 198 | 267.1 | 3450 mss | **131** | **0** | 130338 | 159 |
| Crest no CA | 204.61 | 198 | 267.1 | 3450 mss | 131 | 0 | 130338 | 159 |
| Crest no LSG | 187.15 | 198 | 246.4 | 3233 mss | 124 | 0 | 0 | 224 |
| Crest no anticipator | 276.28 | 198 | 318.5 | 4159 mss | 124 | 0 | 39181 | 0 |
| v3.7 OCE (Crest flags off) | 276.64 | 198 | 314.5 | 4198 mss | 115 | 0 | 0 | 0 |

BBR mode histogram: **1696 / 1800** slots `loss_ignored`. Crest: **441** slots
`congestive_recovery`, 172 `reprobe_explore`, 213 `oce_echo`. p95 is 198 ms for
every variant (path 194 + soft-QIR). Queue excess is not the gp gap.

Crest REPROBE reasons (131 in 90 s — a “hop” every ~0.7 s on `reconfig=0`):

| reason | n | response |
|--------|--:|----------|
| `ep:ack_ia+loss_burst` | **92** | SER-lite (cut 0.80, wipe samples, `bw_est ← 0.90×prior`) |
| `ep:rtt_mad+loss_burst` | 15 | full invalidate (cut 0.58) |
| `ep:loss_burst` | 10 | SER (cut 0.85, wipe samples) |
| `ep:rtt_mad` / `+ack_ia` | 9 | full invalidate |
| other `loss_rtt` mixes | 5 | mix |

`ep:loss_burst` is **not** gated. The storm is the *response*: SER-lite treats
fade overflow + ACK-IA as an epoch reset.

### Hypothesis (cook) — keep / discard

> Crest over-cuts / refuses stretch on the high-OWD far-site window while
> BBR’s max-filter rides through.

| Piece | Verdict | Evidence |
|-------|---------|----------|
| Crest Abort over-cut | **DISCARD** | `ca_aborts=0`. Path never exceeds 1.35× p50. noCA ≡ Crest. |
| LSG refuses stretch | **DISCARD as cause** | 130k clamps are a *symptom* of collapsed `prior_bw`. Turning LSG **off** *loses* 17 Mbps. |
| Freeze-only anticipator | **KEEP (partial)** | 159 holds. Disabling it is +71.7 Mbps (204.61 → 276.28). Still 82 Mbps behind BBR. |
| REPROBE / SER-lite over-cut | **KEEP** | 131 epoch responses on a no-HO trace. SER-lite wipes delivery marks and discounts `bw_est`. Dominant reason is `ack_ia+loss_burst` (fade + 0.0001 loss + 1 MB overflow). |
| BBR max-filter rides through | **KEEP** | BBR `bw_est` mean 384.5 (p95 450) vs Crest 267.1. BBR ignores loss; window is `max(0.5, 10×min_rtt)` **max**. Crest is p82 over `5×min_rtt` and **clears the window on every SER**. |
| TBPR | **not load-bearing** | CA never aborts TBPR. SER-lite re-arms a 2.2×RTT reclaim that is immediately re-cut. |

Cycle on D/600:

1. UDP-sat fade (down to 22.8 Mbps) fills the 1 MB buffer → congestive marks.
2. Crest cuts 0.72× (`congestive_recovery`) and records `loss_burst`.
3. ACK-IA from the fade + `loss_burst` trips SER-lite (cooldown bypassed: score ≥ threshold+1).
4. SER-lite wipes samples, `bw_est ← 0.90×prior`, 0.12 s fill (0.66 RTT at 182 ms).
5. Anticipator holds growth 120 ms on leftover ACK-IA.
6. BBR keeps the max-filter through the cellar and ignores the same marks.

On A/1 (32 ms RTT) the same 0.12 s SER-lite fill is ~4 RTTs and Crest is
slightly *ahead* of BBR. Do not advertise A/1 as a BBR win. The far-site
window is where the hop taxonomy is wrong.

## One targeted lever — FarHold (`use_far_hold`, default False)

**Not** Halo, Pulse, EpochMemory, QSP, PATHHINT, hybrid freeze, WetLinks/Zhao
knobs, or a Crest-Abort/LSG retune.

**FarHold:** when `min_rtt ≥ 80 ms` (far-site; C/599 p50 RTT ≈ 102 ms, D/600 ≈
182 ms; A/B and `starlink_v1` cruise stay below), treat endpoint fade/jitter
detects as a **hold**, not an epoch reset:

1. Detect still fires. `ep:loss_burst` is **not** gated (`reconfigs_detected`
   still increments).
2. `_enter_reprobe` for `ep:*` other than a classic 1.55× jump: **no** sample
   wipe, **no** `bw_est` discount, **no** cwnd cut. `last_reconfig_t` is
   unchanged so the delivery max-window is not discarded.
3. `on_loss` with clean delay (`rtt < 1.25×min_rtt`): no 0.72× congestive cut
   (BBR-like ignore of fade overflow).
4. Freeze-only anticipator does not hold on ACK-IA (far-RTT IA is fade, not HO
   lead).

Threshold 80 ms is a path-RTT floor, not a seed-id branch. Flag **defaults
False**. `run_leocc` opts in for this research cook. Flip the default only if
the same 5-window table is a clear Pareto vs BBR (gp mean clears 379.80, p95
mean ≤ 89.60) **and** terrestrial ≥ 77 with Crest defaults otherwise off.

## 5-window result (FarHold opted in on LeoCC only)

Same 5 catalog-quantile downlink windows. `dt=0.01`. Era buffer 1 MB.
Soft-QIR α=0.20. Endpoint-only. `ep:loss_burst` not gated. Product Crest
default stays `use_far_hold=False`. Terrestrial uses product defaults
(250 KB, seeds 13,7,42,99,123).

| CCA | gp mean | p95 mean |
|-----|--------:|---------:|
| CUBIC | 31.14 | 87.20 |
| BBRv3approx | **379.80** | **89.60** |
| **LeoAware Crest + FarHold** | **377.70** | **89.60** |

Terrestrial LeoAware **78.62** @ 46.0 ms.

| q | site/trace | CUBIC gp/p95 | BBR gp/p95 | Crest+FarHold gp/p95 | v3.13 Crest |
|---|------------|-------------:|-----------:|---------------------:|------------:|
| q00 | A/1 | 49.88 / 34 | 408.33 / 36 | 409.44 / 36 | 409.44 |
| q25 | A/600 | 51.61 / 34 | 338.54 / 38 | 344.50 / 38 | 344.50 |
| q50 | B/600 | 29.56 / 62 | 400.60 / 64 | 391.11 / 64 | 391.11 |
| q75 | C/599 | 16.28 / 110 | 393.25 / 112 | **390.25** / 112 | 340.20 |
| q100 | D/600 | 8.38 / 196 | 358.29 / 198 | **353.18** / 198 | 204.61 |

A/B unchanged (min_rtt below 80 ms). C/599 +50.05 Mbps. D/600 +148.57 Mbps
(353.18 vs BBR 358.29 vs oracle 380.91). D/600 **not** dropped. p95 mean
tied at 89.60 (path-dominated). Integrity: ASCENT-D + Crest defaults off
green. FarHold default stays **False** (not a Pareto).

## Accept / kill (this cook)

Kill / **REJECT** if any of:

- Crest gp mean ≤ BBR 379.80
- Crest p95 mean > 89.60
- D/600 dropped or cherry-picked
- terrestrial Crest < 77 (product 250 KB, seeds 13,7,42,99,123)
- integrity red (ASCENT-D / Crest defaults off)

**Decision: ACCEPT_ERA_REJECT_BBR / REJECT vs BBR.** Crest gp mean **377.70
≤ 379.80**. p95 89.60 = 89.60. Absolute 75/138.8 PASS. Terr 78.62 ≥ 77.
D/600 kept. Integrity green. FarHold recovered 39.73 of the 41.83 Mbps
mean gap and did **not** clear BBR. **Not Current. Not paid. Do not merge.**

**ACCEPT-as-research** only if Crest gp mean **clears** BBR without p95
regression on the same 5 windows. This cook does not.

## Honesty

- Capacity is UDP iperf3 saturation, not dish PHY.
- p95 is 2× ICMP OWD (separate queue). Do not market p95 as CCA delay control.
- Do not mix with `starlink_v1` 82.07/76.26, `wetlinks_v1`, or `zhao_zenodo23`.
- Means, not peaks. Do not advertise A/1 as a BBR win.
- Soft-QIR α frozen 0.20. Era buffer 1 MB (product default stays 250 KB).

## Reproduce

```bash
python -m experiments.test_leocc_integrity
python -m experiments.test_ascent_d_integrity
python -m experiments.diag_d600 --tag 20260814-v314-d600 --workers 4
python -m experiments.run_leocc --tag 20260814-v314-d600 --workers 4
```
