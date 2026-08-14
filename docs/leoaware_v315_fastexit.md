# LeoAware v3.15 — FastExit died; LeanCatch (research-only)

**Date:** 2026-08-14  
**Branch:** `cursor/v315-fastexit-f1ea`  
**Era:** `leocc_v1` (Lai et al., SIGCOMM 2025 / LeoCC). **Not Current. Not paid. Do not merge.**  
**Product lock:** synthetic `starlink_v1` / v3.9 Crest (82.07 gp / 76.26 p95). Do not mix eras.

Cite: Lai, Zeqi; Li, Zonglun; Wu, Qian; Li, Hewu; Li, Jihao; Xie, Xin; Li, Yuanjie;
Liu, Jun; Wu, Jianping. *LeoCC: Making Internet Congestion Control Robust to LEO
Satellite Dynamics*. ACM SIGCOMM 2025. DOI
[10.1145/3718958.3750491](https://doi.org/10.1145/3718958.3750491).
Capacity is **UDP iperf3 saturation**, not dish PHY / RF Mbps. p95 is **2× ICMP
OWD** on a separate Starlink SQM queue (LeoReplayer).

PR #18 FarHold (draft, SHA `01d8567e`) stays a different cook. This PR does not
pile onto it. FarHold 80 ms floor is not lowered. fade-on-reconfig=0 is not
revived. Halo / Pulse / EpochMemory / QSP / PATHHINT / hybrid freeze / WetLinks
knobs are not replayed.

## Hypothesis (non-binding — verified, then discarded)

B/600 leftover vs BBR (391.11 vs 400.60) is Crest’s 0.72× congestive cut
lingering after the fade. **FastExit** = while in `congestive_recovery`, if
measured delivery ≥ ~0.95 × pre-cut `bw_est` (or recent max delivery), exit
recovery / restore cwnd faster. Detect still fires. `ep:loss_burst` is never
gated.

This is **not** FarHold. It must not move A/1 or A/600 gp down (they already
beat BBR: 409.44 / 344.50).

## Diagnosis — B/600 recovery-exit vs A/1

Script: `python3 -m experiments.diag_fastexit`. Archive:
`results/archive/20260814-v315-fastexit/diag/recovery_exit.json`.

Same rails as v3.13 / PR #18: dt=0.01, 1 MB era buffer, Soft-QIR α=0.20,
endpoint-only, Crest defaults.

### When does each leave `congestive_recovery`?

| Window | CCA | gp | cong_rec frac | mean cwnd | n 0.72-cuts | delivery-exit p50 | would FastExit fire | under-windowed fires |
|--------|-----|---:|--------------:|----------:|------------:|------------------:|--------------------:|---------------------:|
| A/1 | Crest | **409.44** | 0.54 | 1283 mss | 4774 | **10 ms** (1 slot) | 4371 | **22 (0.5%)** |
| A/600 | Crest | **344.50** | 0.41 | 1135 mss | 3703 | **10 ms** | 3255 | **59 (1.8%)** |
| B/600 | Crest | 391.11 | **0.73** | 1870 mss | 5791 | **10 ms** | 5466 | **1760 (32%)** |
| A/1 | BBR | 408.33 | 0.00 (`loss_ignored`) | 1760 mss | — | — | — | — |
| B/600 | BBR | 400.60 | 0.00 (`loss_ignored`) | 4023 mss | — | — | — | — |

Delivery vs cwnd:

| Window | mean bw_est | mean delivery | mean cwnd / delivery-BDP |
|--------|------------:|--------------:|-------------------------:|
| A/1 | 442.2 | 411.4 | **1.40** |
| A/600 | 373.3 | 344.7 | **1.45** |
| B/600 | 418.5 | 393.4 | **1.01** |

REPROBE taxonomy is unchanged from PR #18 B/600 note: `ser_lite=0` on all three
windows. A/1 has fade + 28× `ep:loss_burst` and already beats BBR. B/600 is 40×
`ep:loss_burst` + 26× `ep:rtt_mad+loss_burst`. CA=52 on A, CA=0 on B.

### What the numbers say

1. **Nobody “stays in recovery after the fade” in the time-to-exit sense.**
   Delivery is already ≥ 0.95 × pre-cut at the next ACK (p50 = p95 = 10 ms) on
   A and B. The 73% `congestive_recovery` histogram is **re-entry**: the 1 MB
   era buffer is smaller than BDP at ~400 Mbps × 50 ms, so a full-pipe sender
   overflows every slot. BBR ignores those marks (`loss_ignored` 1745/1800).
   Crest applies 0.72× every time.

2. **Blind FastExit would tax A.** The delivery-recovered predicate is true on
   4371 A/1 ACKs and 3255 A/600 ACKs. Restoring cwnd on that predicate is a
   general overflow-undo. A already beats BBR with the 0.72 cut in place.
   Undoing it on A is an A retune. **STOP FastExit.**

3. **The leftover is compounding, not a late exit.** B/600 sits at 1.01×
   delivery-BDP (Crest mean cwnd 1870 vs BBR 4023). A sits at 1.40–1.45× and
   is almost never under 0.70× after a single cut (22 and 59 ACKs). B is
   under-windowed on **32%** of delivery-recovered exits because overflow is
   denser (73% vs 41–54%) and 0.72^n stacks.

## Why FastExit died

FastExit as specified (restore when delivery recovered) is **not** a B-only
lever. It is an A lever that happens to also fire on B. The cook forbids
moving A/1 or A/600 down. A generalized restore would also be a silent
FarHold-without-80ms (overflow ignore), which PR #18 already forbade.

`use_fast_exit` exists as a default-False flag so integrity can assert it is
off. It does **not** restore cwnd. `fast_exits` stays 0.

## Replacement: LeanCatch

**One new mechanism.** After a congestive 0.72× cut, on the next ACK where
delivery ≥ 0.95 × pre-cut `bw_est` **and** `cwnd < 0.70 × live delivery BDP`
**and** delay is clean (`rtt < 1.18 × min_rtt`), restore cwnd toward
`min(pre_cut_cwnd, delivery BDP)`. One-shot per cut. Detect still fires.
`ep:loss_burst` is never gated.

Why this cannot move A: the under-windowed gate is the diagnosis discriminator
(A 0.5–1.8% vs B 32%). A single 0.72 cut from a ~1.4× BDP cruise stays above
0.70×. Only stacked cuts (B’s denser overflow) fall through.

Not FarHold: no `min_rtt ≥ 80` floor, no fade-hold, no sample keep, no
overflow ignore. D/600 SER-lite wipe is a different bug; LeanCatch must not
drop D/600 below 204.61.

Flag: `use_lean_catch` default **False**. `run_leocc` opts in on LeoCC windows
only. Product Crest / terrestrial / `starlink_v1` stay off.

## Rails (unchanged)

- Same 5 catalog-quantile downlink windows (A/1, A/600, B/600, C/599, D/600).
- dt=0.01, 1 MB era buffer (product `buffer_bytes` stays 250 KB).
- Soft-QIR α=0.20. Endpoint-only.
- Terrestrial control: product 250 KB, seeds 13,7,42,99,123, Crest ≥ 77.
- D/600 is not dropped.

## Kill / ACCEPT

| Check | Bar | |
|-------|-----|--|
| LeanCatch gp mean | **clears** BBR **379.80** | else REJECT |
| LeanCatch p95 mean | ≤ **89.60** | else REJECT |
| A/1 gp | ≥ 409.44 | else REJECT |
| A/600 gp | ≥ 344.50 | else REJECT |
| D/600 | present and ≥ 204.61 | else REJECT |
| Terr Crest | ≥ 77 | else REJECT |
| Integrity | ASCENT-D + Crest defaults off, including `use_fast_exit=False` and `use_lean_catch=False` | else REJECT |

ACCEPT is **research-only** on `leocc_v1`. Still not Current. Still not paid.
Still do not merge. Do not mix with starlink_v1 82.07/76.26.

## Reproduce

```bash
python3 -m experiments.test_leocc_integrity
python3 -m experiments.test_ascent_d_integrity
python3 -m experiments.diag_fastexit --tag 20260814-v315-fastexit --workers 3
python3 -m experiments.run_leocc --tag 20260814-v315-fastexit --workers 4
```
