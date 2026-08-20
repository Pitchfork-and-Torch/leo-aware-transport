# LeoAware v3.13 — `leocc_v1` ingest + dual-gate cook (research era)

**Date:** 2026-08-14  
**Branch:** `cursor/v313-leocc-traces-a108`  
**Base:** `main` @ `e7d4cbf` (WetLinks uncap #11)  
**Decision:** `ACCEPT_ERA_REJECT_BBR`. Absolute 75/138.8 **PASS** on means. Crest does **not** clear BBR (337.97 < 379.80 gp). **Not Current. No paid. Do not merge.**

This is **not** a mix with `wetlinks_v1` (hold-expanded 15 s iperf), `zhao_zenodo23`
(PR #12, TCP Cubic goodput, IRTT p95 mean 146.74 FAIL), or synthetic
`starlink_v1` Crest 82.07/76.26 (prior lock). Product Current is now v3.17
FillGap 82.45/76.26. This `leocc_v1` era remains **research-only**.
PR #5 v3.4.1 is leftover WIP — not used here.

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
| Product lock | v3.17 FillGap Current on `starlink_v1` (this era is research-only) |

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

## CCA (means of 5 downlink windows)

Endpoint Crest defaults. `dt=0.01`. Era buffer **1 MB** (send ceiling 800 Mbps)
so ~350–430 Mbps UDP-sat is not clipped by the product 250 KB / 200 Mbps
ceiling. Product `LeoPathConfig.buffer_bytes` stays 250 KB. Soft-QIR α = 0.20.
Seeds are the five catalog windows (not the product 13/7/42/99/123 path RNG).
Terrestrial control uses those product seeds at the product 250 KB buffer.

BBR's per-ACK `max(bw_window)` scan was replaced with an **identity** sliding
max (same value; `test_bbr_max_filter_matches_naive_scan`). Not a CCA retune.
Jobs ran 4-wide (`--workers 4`).

| CCA | gp mean | p95 mean | vs bars |
|-----|--------:|---------:|---------|
| CUBIC | 31.14 | 87.20 | gp FAIL (expected collapse) |
| BBRv3approx | 379.80 | 89.60 | both PASS |
| **LeoAware Crest** | **337.97** | **89.60** | **gp PASS, p95 PASS** |
| terrestrial LeoAware | 78.62 | 46.0 | terr ≥77 PASS |

| Check | Bar | Result |
|-------|-----|--------|
| LeoAware gp mean | ≥ 75 | **PASS** (337.97) |
| LeoAware p95 mean | ≤ 138.8 | **PASS** (89.60) |
| terrestrial gp | ≥ 77 | **PASS** (78.62) |
| Crest gp > BBR | — | **FAIL** (337.97 < 379.80) |
| Crest p95 ≤ BBR | — | **PASS** (89.60 = 89.60) |
| Pareto vs BBR | both | **FAIL** |

### Per-window (not the gate; gate is the mean)

| q | site/trace | CUBIC gp/p95 | BBR gp/p95 | Crest gp/p95 |
|---|------------|-------------:|-----------:|-------------:|
| q00 | A/1 | 49.88 / 34 | 408.33 / 36 | 409.44 / 36 |
| q25 | A/600 | 51.61 / 34 | 338.54 / 38 | 344.50 / 38 |
| q50 | B/600 | 29.56 / 62 | 400.60 / 64 | 391.11 / 64 |
| q75 | C/599 | 16.28 / 110 | 393.25 / 112 | 340.20 / 112 |
| q100 | D/600 | 8.38 / 196 | 358.29 / 198 | 204.61 / 198 |

Crest is slightly ahead on the two low-OWD windows (A/1, A/600) and behind on
B/C/D. The D/600 far-site tail (path p95 194 ms) is where Crest leaves the most
UDP-sat on the table (204.61 vs BBR 358.29). Do not drop D/600. Do not advertise
the A/1 peak as a BBR win.

**Decision: ACCEPT_ERA_REJECT_BBR.** Absolute dual-gate holds on this era.
Crest is not a Pareto improvement vs BBR. Not Current. No paid. Do not merge.

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
python -m experiments.run_leocc --tag 20260814-v313-leocc --workers 4
```
