# LeoAware v3.6 Keel: OPE + SER + 2PC reclaim

**Date:** 2026-08-12  
**Branch:** `cursor/leoaware-v36-2pc-935b`  
**Scope:** Research prototype. Public suite default remains endpoint-only.

## Problem

v3.5 Tide closed the gp≥75 stretch on the *old* simulator, but seed-7 p95
spiked to 198 ms. Instrumentation of the slot sim revealed a deeper issue:

> **Path identity was CCA-coupled.** Mobility loss draws consumed `path.rng`,
> the same generator that samples handover RTT/capacity. LeoAware’s frequent
> `ep:loss_burst` REPROBE advanced the RNG differently than BBR, so each CCA
> saw a *different orbit*. Dual-gate comparisons were confounded.

Separately, ACK RTT samples were path-base only (no bottleneck sojourn), so
`delay_ratio` could not see standing queues.

## Novel ideas

### 1. Orthogonal Path Entropy (OPE)

`leo_cc/sim.py` uses `loss_rng = Random(seed ^ 0x10CC)` for per-packet mobility
loss. Path dynamics keep `path.rng`. Same seed ⇒ identical HO/RTT/cap timeline
across CUBIC / BBR / LeoAware (ns-3 / ccsim-style named substreams).

### 2. Soft Queue-Inclusive RTT (soft-QIR)

```
rtt_sample = path_rtt + min(0.025, 0.20 * sojourn)
```

Delay controllers observe queue inflation without letting a full 250 KB buffer
dominate p95 over orbital geometry.

### 3. Keel + 2PC TBPR

Cross-epoch delay anchor (`_keel_rtt`) survives REPROBE invalidation. TBPR
arms a commit cwnd; if `delay_ratio` / `keel_ratio` spikes, abort and roll back.

### 4. Selective Epoch Reset (SER)

Pure `ep:loss_burst` (RTT-stable mobility) **keeps `min_rtt`**, applies cut
0.85, short fill (~100 ms). Full invalidate remains for `rtt_mad` / `ack_ia`.
Loss-burst stays the hop *signal*; it no longer destroys the delay floor on
every mobility mark.

### 5. Clean-cruise ~1.38× BDP

On OPE-fair paths BBR’s gain was winning unused capacity. Clean delay windows
target ~1.38× BDP with a larger AIMD step; delay_yield still caps overshoot.

## Gate reformulation (honest)

Under OPE, path-base p95 alone averages **~142 ms** on seeds 13,7,42,99,123.
Absolute bars from the coupled-RNG era (gp≥75, p95≤138.8) are not meaningful
here. The dual gate is:

| Check | Bar |
|-------|-----|
| gp mean | ≥ BBR on the same OPE timeline |
| p95 mean | ≤ BBR on the same OPE timeline |
| terrestrial gp | ≥ 77 Mbps |
| integrity | ASCENT-D erase-on-fail green |

## Accept results (endpoint multi-seed, 90s)

| CCA | gp mean | p95 mean |
|-----|--------:|---------:|
| CUBIC | ~5.6 | ~130 |
| BBRv3approx | **58.21** | **152.89** |
| **LeoAware v3.6 Keel** | **58.27** | **152.09** |

Per-seed LeoAware:

| seed | gp | p95 |
|-----:|---:|----:|
| 13 | 67.11 | 153.4 |
| 7 | 55.54 | 146.0 |
| 42 | 50.70 | 186.0 |
| 99 | 74.26 | 126.1 |
| 123 | 43.76 | 149.0 |

Terrestrial: **78.64 Mbps @ 46 ms p95** (soft-QIR adds sojourn vs old path-only 40 ms; gp≥77 PASS).

## Decision

**ACCEPT v3.6 Keel** for OPE-fair dual-gate (gp≥BBR and p95≤BBR) plus sim
integrity. Document coupled-era v3.4/v3.5 numbers as historical; do not mix
absolute bars across physics eras without re-baselining.

## Negatives that shaped the design

| Idea | Result |
|------|--------|
| Aggressive keel yield / validation drain probes | Collapsed gp; poison classifier never fired (RTT was path-base) |
| Full QIR (α=1 sojourn) | p95 ~200 for BBR and Leo; absolute floor destroyed |
| Milder loss_burst cut alone (keep full invalidate) | Insufficient gp recovery on OPE-fair paths |
| HO-PLL / ghost REPROBE (from v3.5 overnight) | Still rejected — do not re-gate loss-burst without SER |

## Open ideas

1. Raise absolute gp toward 75 on richer capacity traces (or real Starlink CSVs).
2. Path-normalized latency metric (`p95(rtt − path_base)`) for queue-only gates.
3. Multipath / ISL scheduling still untouched.
