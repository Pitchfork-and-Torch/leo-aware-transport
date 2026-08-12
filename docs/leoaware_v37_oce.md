# LeoAware v3.7 OCE: Orbit Capacity Echo + SER-lite

**Date:** 2026-08-12  
**Branch:** `cursor/leoaware-v37-oce-935b`  
**Scope:** Research prototype. Builds on v3.6 Keel (OPE + soft-QIR + SER).

## Problem

v3.6 Keel passed the OPE-fair dual gate, but only by a thin margin
(58.27 / 152.09 vs BBR 58.21 / 152.89). Seeds 13/7 still trailed BBR on
goodput; seed 42 spent many hops in full `ack_ia+loss_burst` invalidate
despite RTT-stable mobility.

## Novel ideas

### 1. Orbit Capacity Echo (OCE)

After SER / SER-lite, arm a ~3 RTT echo window with a commit cwnd:

- If `delay_ratio < 1.14` and delivery rate exceeds `bw_est`, blend rate into
  `bw_est` and step cwnd toward **1.42× BDP** (with optimistic pacing).
- If `delay_ratio > 1.30`, abort and roll cwnd back to the OCE commit point.

Transactional capacity chase — not a permanent gain raise (avoids DTCE / QCP
failure modes).

### 2. SER-lite

`ack_ia+loss_burst` without `rtt_mad` / `loss_rtt` keeps `min_rtt` (ACK freeze
≠ path RTT jump). Cut 0.80, short fill. Pure `ep:loss_burst` stays SER 0.85.
True RTT-jump reasons still full-invalidate.

## Accept results (endpoint, 90s, OPE-fair)

| CCA | gp mean | p95 mean | Δ vs BBR |
|-----|--------:|---------:|----------|
| BBRv3approx | 58.21 | 152.89 | reference |
| LeoAware v3.6 Keel | 58.27 | 152.09 | +0.06 / −0.80 |
| **LeoAware v3.7 OCE** | **58.78** | **152.09** | **+0.57 / −0.80** |

Per-seed LeoAware v3.7:

| seed | gp | p95 |
|-----:|---:|----:|
| 13 | 67.19 | 153.4 |
| 7 | 56.40 | 146.0 |
| 42 | 51.69 | 186.0 |
| 99 | 74.85 | 126.1 |
| 123 | 43.76 | 149.0 |

Terrestrial: **~78.65 Mbps @ 46 ms** (gp≥77 PASS). Integrity green.

## Decision

**ACCEPT v3.7 OCE** — widens the OPE-fair dual-gate win without re-gating
loss-burst detection or raising REPROBE fill ceilings.

## Open ideas

1. Close remaining seed-13 gp gap to BBR (~1 Mbps).
2. Seed-42 p95 is largely path geometry (BBR also ~184); need richer traces
   or path-normalized excess-RTT metric for further latency claims.
3. Real Starlink CSVs under OPE.
