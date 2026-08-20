# LeoAware v3.16 OpenSlot — starlink_v1 product-era cook

**Date:** 2026-08-14  
**Branch:** `cursor/v316-starlink-e853`  
**Era:** synthetic `starlink_v1` (same harness / seeds as the v3.9 Crest lock)  
**Lever:** **OpenSlot** (`use_openslot`, default **False**)  
**Decision:** **REJECT vs BBR** (82.38 ≤ 82.44; p95 76.26 ≤ 76.66; terr 79.05).  
**Not Current. Not paid. Do not merge.**

## Lock we are chasing

v3.9 Crest lock (`results/archive/20260812-v39-starlink-v1/`):

| CCA | gp mean | p95 mean |
|-----|--------:|---------:|
| BBRv3approx | **82.44** | **76.66** |
| LeoAware v3.9 Crest | 82.07 | 76.26 |

Seeds **13, 7, 42, 99, 123**. `leo_fast_ho` 90s. Soft-QIR α=0.20. Endpoint-only.
Dual-gate gp≥75 AND p95≤138.8 still holds; this cook’s research bar is
**Crest mean gp > 82.44 AND p95 ≤ 76.66**. Terr ≥ 77. Means, not peaks.

This is a **synthetic** `starlink_v1` harness, not dish PHY. No `leocc_v1`
numbers in the product table.

## Diagnosis (measured, not leftover theater)

`python3 -m experiments.diag_v316_starlink`  
Archive: `results/archive/20260814-v316-starlink/diag/diagnosis.json`

Per-seed lock gap (Crest − BBR gp): 13 **−0.67** · 7 **−0.07** · 42 **−0.58** ·
99 **−0.16** · 123 **−0.39** (tip 85.28 vs 85.57). p95 is path-tied on 13/7/42/99;
seed 123 is the only p95 edge (Crest 79.65 vs BBR 81.65).

| Hypothesis | Verdict | Evidence |
|------------|---------|----------|
| **H1** Crest soft-pace binds `can_send` below cwnd; BBR has no pace bind | **CONFIRMED** | pace_bind_frac **0.984**; cwnd_bind **0.008**; clean_underfill **0.708** |
| **H2** First-2s starve (1.28× / p82 / 1.08× pace vs BBR 2× / max-filter / no pace) | **PARTIAL** | mean first2 55.67 vs 58.51; **seed 42 is 41.3 vs 58.5**; other seeds Crest is slightly *ahead* |
| **H3** Crest p82 `bw_est` sits below BBR max-filter | **DISCARDED** | Crest mean bw_est **97.0** ≥ BBR **96.1**. CCH/Halo already rejected raising the filter here. |
| **H4** REPROBE/SER time is the 0.37 Mbps | **WEAK** | reprobe ACK frac **0.023**; reprobe-mode frac **0.003**; CA aborts **0** |

Crest util 0.9765 vs BBR 0.9801. Crest loss 1.18% vs BBR 1.42%. Crest mean
excess RTT 4.61 vs 4.80 ms. Crest is the more conservative sender on the
**same** OPE orbit; the bind is pace, not a low bandwidth estimate.

v3.9 Crest ablation already showed DLC+LSG trims ~0.3 Mbps / 0.4 ms p95 vs
v3.7-style flags-off (82.28 / 76.66). That is not enough to clear BBR, and
turning Crest flags off is not a new lever.

## What OpenSlot is

One named lever. Opt-in. Default **False**.

When the last ACK is delay-clean (`rtt / min_rtt < 1.12`, no high-delay
streak, not in REPROBE, not in CA hold) **and** inflight < 0.80× BDP,
`can_send` returns cwnd room (no pace bind). BBR in this sim is already
cwnd-only (`BaseCCA.can_send`).

Killed before the archive, same name:

- unconstrained unbind (no slack gate): seed 13 **96.20** vs Crest 96.65
- extra 2.5× burst on clean-but-not-slack slots: seed 13 **96.15**; mean 82.34

Official archive (`python3 -m experiments.run_starlink`): OpenSlot
**82.38 / 76.26** vs BBR **82.44 / 76.66**. Terr **79.05**. Helps 7/99/123
past BBR; seed 13 leftover is a cwnd gap (~0.62), not pace. Short
**0.06 Mbps**.

**Decision: REJECT vs BBR.** Default stays False. Not Current. Do not merge.

OpenSlot does **not**:

- gate `ep:loss_burst` or any detect path
- skip REPROBE / fade-on-reconfig
- raise cruise BDP or change the p82 filter (CCH / Pulse / p90 — rejected)
- invert sojourn into a pace discount (QSP — rejected)
- special-case `reconfigs_detected==0` or a 1.5 s first-epoch window
  (WetLinks SpikeHold — forbidden replay)
- generalize FarHold / FastExit / LeanCatch

## Integrity

`LeoAwareCCA()` keeps `use_openslot=False`. Product `run_suite` / default
`multi_seed` stay Crest. This cook’s archive runner
(`python3 -m experiments.run_starlink`) opts in for measurement only.
ASCENT-D + OPE tests must stay green with the flag off.

## Reproduce

```bash
python3 -m experiments.test_ascent_d_integrity
python3 -m experiments.diag_v316_starlink
python3 -m experiments.run_starlink
```

Archive: `results/archive/20260814-v316-starlink/`
