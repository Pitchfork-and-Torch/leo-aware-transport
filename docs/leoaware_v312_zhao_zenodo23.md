# LeoAware v3.12 — `zhao_zenodo23` ingest + geometry (research era only)

**Date:** 2026-08-13  
**Branch:** `cursor/v312-zhao-zenodo23-db91`  
**Base:** `main` @ `55b3fc45`  
**Decision:** geometry **landed**. Dual-gate on this era: **INCONCLUSIVE** on gp (TCP Cubic goodput is a lower bound, mean 30.37 < 75) and **FAIL** on IRTT p95 (mean 146.74 > 138.8). **No CCA on this cook.** **Do not merge.** **Ping Optimizer.**

This is **not** a Current-tab bump, **not** paid copy, **not** a mix with `wetlinks_v1` (PR #11) or synthetic `starlink_v1` / v3.9 Crest (PR #9, 82.09/76.26). Product lock stays where it is.

## Citation

Dataset (CC-BY-4.0):

- Zhao, Jinwei; Pan, Jianping (2023). *Starlink Latency and Downlink Throughput Measurement Dataset* (v20230917). Zenodo. DOI [10.5281/zenodo.10020034](https://doi.org/10.5281/zenodo.10020034). https://zenodo.org/records/10020034

Paper:

- Pan, Jianping; Zhao, Jinwei; Cai, Lin. *Measuring a Low-Earth-Orbit Satellite Network*. IEEE PIMRC 2023. https://arxiv.org/abs/2307.06863 — DOI [10.1109/PIMRC56721.2023.10294034](https://doi.org/10.1109/PIMRC56721.2023.10294034)

## What this PR is

Ingest + path geometry only, from the Optimizer ACCEPT dump of 2026-08-13.

| | |
|--|--|
| Era | `zhao_zenodo23` |
| Dump | `data-20230913-20230917.tar.zst` (~1.17 GB packed, ~9.7 GB uncompressed). **Not vendored.** MD5 `7c1fecd817616b49eecd414ecda31c6d` matched Zenodo. |
| Path | Victoria Ethernet dish → Seattle PoP → GCP `us-west1-a` |
| Probes | concurrent IRTT (UDP, 10 ms) + iPerf3 (TCP Cubic, `-R` downlink, 100 ms reports), 120 s every 10 min, NTP |
| SQM / CAKE | **unknown** (upstream README does not confirm) |
| Capacity column | `cubic_goodput_mbps` (= `capacity_mbps` by construction) = TCP Cubic downlink goodput. **Not** UDP saturation. **Not** dish PHY / RF Mbps. |
| Oracle | ∫ cubic-goodput series = **lower bound** on path capacity |
| Replay | `LeoPathConfig(trace_csv=..., dt_s=0.05)` |
| CCA | **none** (no Crest, no BBR, no sim CUBIC replay — the path already *is* Cubic’s achieved rate) |

## JSON fields (inspected on the dump, not hypothesized)

IRTT (`irtt` 0.9.0):

- `round_trips[].delay.rtt` — nanoseconds
- `round_trips[].lost` — string (`false` / `true` / `true_up` / `true_down`)
- `round_trips[].timestamps.client.send.wall` — Unix ns
- `stats.duration` — ns

iPerf3:

- `intervals[].sum.bits_per_second` (and `start`/`end` seconds)
- `start.timestamp.timesecs`
- `end.sum_received.seconds`
- `end.sender_tcp_congestion` / `receiver_tcp_congestion` — **`cubic` on all 716 sessions**
- `start.test_start.reverse = 1` (downlink)

plot.py in the Zenodo record uses the same fields (`delay.rtt / 1e6` for ms; `intervals[].sum.bits_per_second / 1e6` for Mbps).

## Validity filter and calendar quantiles

716 IRTT + 716 iperf3 files, **716 identical-timestamp pairs**. All pairs had IRTT duration ≥ 120.3 s and iperf duration ≥ 120.0 s. Validity bar was ≥ 90 s; **716 / 716 passed**. Not a cherry-pick of one pretty session.

**Quantile rule (stated, applied):** calendar, by session **start time**, not by mean cubic goodput.

Sort valid sessions by UTC timestamp in the filename. Nearest-rank

```
idx = min(n - 1, int(q * (n - 1) + 0.5))   # round-half-up
```

at q ∈ {0, 0.25, 0.50, 0.75, 1.00} into n = 716 → indices **0, 179, 358, 536, 715**.

## Resample

- Grid `dt = 0.05` s over the IRTT∩iperf overlap (~119.4–119.8 s).
- IRTT: last non-lost sample with send-wall ≤ t (10 ms → 50 ms ZOH). Lost probes skipped, not interpolated.
- iPerf3: **hold-within-bin** of the 100 ms interval containing t.
- `loss_p = 0` — IRTT UDP loss is not a labeled bottleneck-loss process for the TCP series.
- `reconfig = 0` always — **no invented HO flags** from TCP dips. The dump does not label handovers.

Native IRTT p95 (10 ms, non-lost) is the geometry p95. Resampled path p95 is reported as a diagnostic only (WetLinks-style hold-expand would smear spikes; we do not use it as the bar).

## Geometry table (no CCA)

Archive: `results/archive/20260813-v312-zhao-zenodo23-geom/`

Product bars unchanged: gp mean ≥ 75 **and** p95 mean ≤ 138.8 (here p95 = native IRTT).

| q | session_id | start UTC | oracle cubic-gp Mbps | IRTT p95 ms | resampled oracle | resampled path p95 |
|---|------------|-----------|---------------------:|------------:|-----------------:|-------------------:|
| q00 | `2023-09-13-00-40-00` | 2023-09-13T00:40:00Z | 36.00 | 54.23 | 36.08 | 54.72 |
| q25 | `2023-09-14-06-30-00` | 2023-09-14T06:30:00Z | 38.16 | 64.20 | 38.21 | 64.44 |
| q50 | `2023-09-15-12-20-00` | 2023-09-15T12:20:00Z | 36.43 | 395.35 | 36.49 | 419.67 |
| q75 | `2023-09-16-18-00-00` | 2023-09-16T18:00:00Z | 28.16 | 81.55 | 28.24 | 82.83 |
| q100 | `2023-09-17-23-50-00` | 2023-09-17T23:50:00Z | 13.11 | 138.37 | 13.05 | 141.30 |
| **mean** | | | **30.37** | **146.74** | **30.41** | **152.59** |

### Verdict

| Check | Bar | Result |
|-------|-----|--------|
| oracle cubic-gp mean | ≥ 75 | **INCONCLUSIVE** (30.37). Lower bound, not FAIL. A later UDP/PHY series could sit higher; this dump cannot prove gp≥75 is impossible. |
| IRTT p95 mean | ≤ 138.8 | **FAIL** (146.74). Native 10 ms IRTT, not CCA ACK p95. |
| dual-gate | both | **not PASS** |
| SQM | disclosed | **unknown** |
| dish / RF Mbps | forbidden | **not claimed** |

If cubic-goodput oracle were ≥ 75, gp PASS would be conservative (lower bound). It is not.

### Honesty about q50

q50 median IRTT is **37.4 ms** (ordinary Starlink cruise) but p95 is **395 ms**, with 1676 lost IRTT probes vs ~70–200 on the other four slices. That session is a real calendar midpoint, not a parse bug. Dropping it would move IRTT p95 mean to ~84.6 ms (would PASS the 138.8 bar). **We do not drop it.** Calendar quantiles exist so the cook cannot hide the ugly 120 s window.

q100 cubic goodput 13.11 Mbps is likewise a real campaign endpoint, not a PHY number.

## What this PR does not do

- No Crest vs BBR vs CUBIC sim. Sim CUBIC on this era is contaminated.
- No mix with WetLinks uncap numbers or `starlink_v1` Crest 82.09/76.26.
- No Current / paid / merge.
- No invented traces (Zenodo 200; MD5 matched; dump then deleted from the working tree).
- No 9.7 GB blob in git. Vendored: 5 CSVs + `MANIFEST.md` + `session_stats.json` (~0.5 MB).

Reproduce geometry from vendored slices:

```bash
python -m experiments.zhao_zenodo23_geometry
```

Re-slice from the dump (optional):

```bash
python -m experiments.zhao_zenodo23_ingest --extract-dir /tmp/zhao_zenodo23/extract
```

## Ask for Optimizer

Geometry landed on a real Starlink access era. Cubic-goodput oracle ~30 Mbps mean does **not** unlock gp≥75 as a conservative PASS; IRTT p95 mean fails 138.8 because one calendar session is a 395 ms tail. Product lock stays synthetic `starlink_v1` / v3.9 Crest until Optimizer says otherwise.

**Ping Optimizer. Do not start Crest/BBR on this era.**
