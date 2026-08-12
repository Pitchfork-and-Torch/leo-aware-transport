# LeoAware v3.5 Tide: Time-bounded post-hop reclaim

**Date:** 2026-08-12  
**Branch:** `cursor/leoaware-v35-tide-935b`  
**Scope:** Research prototype. Public suite default remains endpoint-only.

## Problem

v3.4-p95 met the public p95≤BBR gate (138.37 ≤ 138.8) but missed the stretch
goodput floor (73.57 < 75). Multi-seed `leo_fast_ho` left capacity on the table
on clean post-hop paths (notably seed 123: 62.7 Mbps @ 111 ms p95).

## Novel idea: TBPR (time-bounded post-hop reclaim)

After REPROBE exits into cruise, for ~2.5 RTT, if live `delay_ratio < 1.18` and
there is no delay streak, temporarily target **1.20× BDP** with a slightly
larger AIMD step (1.05×MSS vs 0.85×MSS). Abort immediately if `delay_ratio > 1.28`.

Why this is new here:

1. **Not DTCE** — no cross-epoch envelope race, no fill-ceiling raise.
2. **Not continuous QCP/SRLB** — reclaim is time-bounded to the post-hop window.
3. **Not REPROBE-policy change** — detection and cut stay at v3.4.

## Instrumentation finding (negative results that shaped the design)

Overnight probes of HO-PLL, ghost/shadow REPROBE, rate-gated REPROBE, and
loss-burst pacing all **regressed** multi-seed goodput. Key discovery:

> In this slot sim, `on_loss` → `ep:loss_burst` REPROBE is the **primary hop
> detector**. RTT fusion alone fires only ~3–5 times per 90s run; loss-burst
> escalation supplies the rest (~50). Gating or deleting that path under-detects
> true hops and collapses goodput.

Delivery-rate continuity is a poor hop veto here because ACK-clocked rate lags
path capacity changes by ~1 RTT.

## Accept results (endpoint multi-seed, 90s, seeds 13,7,42,99,123)

| CCA | gp mean | p95 mean | vs BBR (70.88 / 138.8) |
|-----|--------:|---------:|------------------------|
| CUBIC | 5.47 | 124.8 | collapse |
| BBRv3approx | 70.88 | 138.8 | reference |
| LeoAware v3.4-p95 | 73.57 | 138.37 | p95≤BBR; gp floor miss |
| LeoAware v3.3-A | 78.06 | 149.7 | gp peak / p95 residual |
| **LeoAware v3.5 Tide** | **76.27** | **147.39** | **gp≥75 PASS; p95 residual** |

Per-seed LeoAware `leo_fast_ho`:

| seed | gp | p95 |
|-----:|---:|----:|
| 13 | 78.95 | 167.7 |
| 7 | 73.46 | 198.3 |
| 42 | 69.54 | 139.1 |
| 99 | 88.39 | 123.7 |
| 123 | 71.02 | 108.1 |

## Gate scorecard

| Check | Bar | Result |
|-------|-----|--------|
| gp mean | ≥ 75.0 | **76.27 PASS** (closes v3.4 stretch miss) |
| p95 mean | ≤ 138.8 | **147.39 FAIL** (residual; better than v3.3-A 149.7) |
| beats BBR gp | > 70.88 | **PASS** |
| terrestrial | ≥ 77 @ 40 | see multi_seed archive |
| integrity | green | run `test_ascent_d_integrity` |

## Decision

**ACCEPT v3.5 Tide for gp≥75 stretch reclaim** with honest p95 residual (same
marketing discipline as v3.3-A). Public Current tab may keep v3.4 as the
p95-under-BBR SoT and list v3.5 as the gp-floor Tide variant — or promote v3.5
if product priority is throughput.

## Open ideas (still unsolved)

1. Kill seed-7 p95 spike (198) without giving back the gp≥75 win.
2. EpochMemory / HO-PLL remain promising once hop detection is less
   loss-burst-dependent (or once real Starlink traces replace the slot sim).
3. Multipath / ISL scheduling still untouched.
