# LeoAware v3.13 — `leocc_v1` ingest + dual-gate cook (research era)

**Date:** 2026-08-14  
**Branch:** `cursor/v313-leocc-traces-a108`  
**Base:** `main` @ `e7d4cbf` (WetLinks uncap #11)  
**Decision:** see scorecard. **Not Current. No paid. Do not merge.**

This is **not** a mix with `wetlinks_v1` (hold-expanded 15 s iperf), `zhao_zenodo23`
(PR #12, TCP Cubic goodput, IRTT p95 mean 146.74 FAIL), or synthetic
`starlink_v1` / v3.9 Crest 82.09/76.26 (PR #9, still open). Product lock stays
where it is. PR #5 v3.4.1 is leftover WIP — not used here.

## Hypothesis

A public **continuous ≥90 s UDP-saturation + RTT** Starlink dump exists
(LeoCC / LeoReplayer, SIGCOMM 2025) and can be sliced into five catalog-quantile
downlink windows for the absolute bars **gp mean ≥ 75 AND p95 mean ≤ 138.8**
without inventing traces, without PATHHINT, and without touching Crest defaults.

If geometry fails either bar → STOP, no CCA, no quiet rebaseline.

## Citation

- Lai, Zeqi; Li, Zonglun; Wu, Qian; Li, Hewu; Li, Jihao; Xie, Xin; Li, Yuanjie; Liu, Jun; Wu, Jianping.
  *LeoCC: Making Internet Congestion Control Robust to LEO Satellite Dynamics*.
  ACM SIGCOMM 2025. DOI [10.1145/3718958.3750491](https://doi.org/10.1145/3718958.3750491).
- Code (MIT): https://github.com/SpaceNetLab/LeoCC
- Traces: https://cloud.tsinghua.edu.cn/d/9fc6fd096e764f57bd25/ (`4.8K.zip`, ~699 MB).
  **Not vendored.**

## What this is (and is not)

| | |
|--|--|
| Era | `leocc_v1` |
| Capacity | UDP iperf3 saturation (mahimahi 12 Mbps/line). **Not** TCP Cubic. **Not** dish PHY / RF Mbps. |
| Delay | ICMP one-way delay, 10 ms bins. **`rtt_ms = 2 × owd_ms`**. |
| SQM | ICMP is on a **separate** Starlink queue (LeoReplayer README). Delay is base path, not CCA-queued RTT. |
| Window | first **90 s** of each ~120 s trace |
| HO flags | **none invented** (`reconfig=0`) |
| Direction | **downlink only** (stated before looking at gp/p95) |
| Product lock | unchanged (`starlink_v1` / v3.9 Crest) |

zhao_zenodo23 is the wrong dump for this cook (Cubic goodput + IRTT p95 FAIL).
WetLinks is 15 s UDP hold-expanded, not continuous 90 s. LeoCC is the first
public dump that matches the leftover ask: concurrent heavy UDP + light ICMP,
~120 s.

## Validity + quantile rule (not cherry-picks)

8 dirs × 600 = 4800 traces. Downlink catalog = 4 sites × 600 = **2400**.
Duration ≥ 90 s on `delay_*.txt`: **2398 / 2400**. Excluded (short delay, not
dropped for gp/p95): `D/16` (75.92 s), `D/212` (88.39 s).

Sort valid by `(site A..D, trace_no 1..600)`. Nearest-rank

```
idx = min(n - 1, int(q * (n - 1) + 0.5))
```

at q ∈ {0, 0.25, 0.50, 0.75, 1} → indices **0, 599, 1199, 1798, 2397**.

Uplink (2400 traces) is a different bottleneck class (LeoReplayer: higher
uplink loss, lower sat). Not mixed into the five-window mean.

## Geometry (no CCA)

Archive: `results/archive/20260814-v313-leocc/`

Bars unchanged: gp mean ≥ 75 **and** p95 mean ≤ 138.8 (p95 = **native 2×OWD**).

| q | site | trace | oracle UDP-sat Mbps | OWD p95 ms | 2×OWD p95 ms |
|---|------|------:|--------------------:|-----------:|-------------:|
| q00 | A | 1 | 425.83 | 16.00 | 32.00 |
| q25 | A | 600 | 353.33 | 16.00 | 32.00 |
| q50 | B | 600 | 408.26 | 30.00 | 60.00 |
| q75 | C | 599 | 406.40 | 54.00 | 108.00 |
| q100 | D | 600 | 380.91 | 97.00 | 194.00 |
| **mean** | | | **394.95** | **42.60** | **85.20** |

| Check | Bar | Result |
|-------|-----|--------|
| oracle UDP-sat mean | ≥ 75 | **PASS** (394.95) |
| 2×OWD p95 mean | ≤ 138.8 | **PASS** (85.20) |
| dual-gate | both | **PASS (geometry)** |

q100 D/600 is **194 ms** (above 138.8). That is a real far-site calendar
endpoint, not a parse bug. Dropping it would be a cherry-pick. The bar is
the **mean**. Soft-QIR α frozen 0.20.

## CCA

Endpoint Crest defaults. `dt=0.01`. Era buffer **1 MB** (send ceiling 800 Mbps)
so ~350–430 Mbps UDP-sat is not clipped by the product 250 KB / 200 Mbps
ceiling. Product `LeoPathConfig.buffer_bytes` stays 250 KB.

Numbers: `results/archive/20260814-v313-leocc/scorecard.json` and `TABLE.md`.

## Honesty

- No dish Mbps claims.
- No OPE-fair / v3.4 mix as product proof.
- No goodput-only "beats BBR" claim.
- Halo / WetLinks uncap / PATHHINT leftovers stand. This cook does not revive them.
- Do not promote `leocc_v1` to Current. Do not merge.

## Reproduce

```bash
mkdir -p /tmp/leocc
curl -L -o /tmp/leocc/4.8K.zip \
  'https://cloud.tsinghua.edu.cn/d/9fc6fd096e764f57bd25/files/?p=/4.8K.zip&dl=1'
python -m experiments.slice_leocc --zip /tmp/leocc/4.8K.zip
python -m experiments.test_leocc_integrity
python -m experiments.run_leocc --geometry-only --tag 20260814-v313-leocc
python -m experiments.run_leocc --tag 20260814-v313-leocc
```
