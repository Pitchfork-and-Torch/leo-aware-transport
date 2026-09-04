# LeoAware v3.18 SoftCeil — starlink_v1 leftover after FillGap

**Date:** 2026-09-04  
**Branch:** `cursor/v318-softceil-bee0`  
**Era:** synthetic `starlink_v1` (same harness / seeds as the v3.17 FillGap lock)  
**Lever:** **SoftCeil** (`use_soft_ceil`, default **False**)  
**Decision:** pending official `run_starlink` archive (see below).

## Lock we are chasing

v3.17 FillGap Current (`results/archive/20260814-v317-fillgap/`):

| CCA | gp mean | p95 mean |
|-----|--------:|---------:|
| BBRv3approx | **82.44** | **76.66** |
| LeoAware v3.17 FillGap (Current) | **82.45** | **76.26** |

FillGap closed the OpenSlot leftover (82.38 → 82.45) but seed 13 is still
**96.80 vs BBR 97.31** (−0.51). Mean edge vs BBR is +0.01. FillGap 0.85 and
OpenSlot 0.80 stay frozen. Do not revive unconstrained unbind or 2.5× burst.

Seeds **13, 7, 42, 99, 123**. `leo_fast_ho` 90s. Soft-QIR α=0.20. Endpoint-only.
Research bar: **mean gp > 82.44 AND p95 ≤ 76.26** (no FillGap p95 regress)
AND seed 13 ≥ **96.80**. Terr ≥ 77. Means, not peaks.

This is a **synthetic** `starlink_v1` harness, not dish PHY. No `leocc_v1`
numbers in the product table. Current stays FillGap unless this cook clearly
widens the BBR margin. Not a paid dual-gate claim.

## Diagnosis (measured)

`python3 -m experiments.diag_v318_softceil`  
Archive: `results/archive/20260904-v318-softceil/diag/diagnosis.json`

FillGap + OpenSlot left on (0.85 / 0.80 untouched). SoftCeil off during
diagnosis. Same five seeds.

Hypothesis:

| Hypothesis | Ask |
|------------|-----|
| **H1** | Seed 13 leftover after FillGap is cwnd sitting in the 0.85–0.90 delivery-BDP band on delay-clean, delivery-caught ACKs. |
| **H2** | Seeds 7/99/123 already beat BBR; they are not the leftover that needs SoftCeil. |

Verdicts and per-seed table are filled from the diagnosis archive after the
run. Do not invent them here.

## What SoftCeil is

One named lever. Opt-in. Default **False**.

When the last ACK is delay-clean (`rtt / min_rtt < 1.12`, no high-delay
streak, not in REPROBE, not in CA hold) **and** measured delivery ≥ 0.95 ×
`bw_est` **and** cwnd is in the leftover band **[0.85×, 0.90×)** delivery BDP
(`delivery × min_rtt / 8`), add **1 MSS**, capped at the 0.90× ceiling.
One packet. Not a burst. Fill-family applies at most one MSS per ACK
(FillGap first if still below 0.85).

Not a pace unbind. Does not retune FillGap 0.85. Does not retune OpenSlot
0.80. Never gates `ep:loss_burst`.

SoftCeil does **not**:

- skip REPROBE / fade-on-reconfig
- raise the p82 filter (CCH / Pulse / p90 — rejected)
- invert sojourn into a pace discount (QSP — rejected)
- special-case `reconfigs_detected==0` or a first-epoch window (SpikeHold)
- generalize FarHold / FastExit / LeanCatch / Halo / PATHHINT
- revive unconstrained unbind or 2.5× burst
- retune FillGap 0.85 or OpenSlot 0.80

## Integrity

`LeoAwareCCA()` keeps `use_soft_ceil=False`, `use_fill_gap=False`, and
`use_openslot=False`. Default `run_suite` / `multi_seed` stay on the Crest
constructor path. Current scorecard numbers stay
`python3 -m experiments.run_starlink` with FillGap + OpenSlot. SoftCeil
archive opts in all three; constructor defaults stay False.

## Official archive

`python3 -m experiments.run_starlink`

Numbers are written by the runner to
`results/archive/20260904-v318-softceil/`. Do not claim ACCEPT vs BBR or a
Current bump until that archive is filled.

## Reproduce

```bash
python3 -m experiments.test_ascent_d_integrity
python3 -m experiments.test_ope_integrity
python3 -m experiments.diag_v318_softceil
python3 -m experiments.run_starlink
```

Archive: `results/archive/20260904-v318-softceil/`
