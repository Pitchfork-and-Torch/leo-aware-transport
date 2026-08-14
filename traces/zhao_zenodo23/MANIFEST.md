# zhao_zenodo23 — vendored replay slices

Research-era Starlink access traces. **Not** a product lock. **Do not merge**
into Current / paid copy. **Do not mix** with `wetlinks_v1` or synthetic
`starlink_v1` scorecards.

## Citation (required)

Dataset:

- Zhao, Jinwei; Pan, Jianping (2023). *Starlink Latency and Downlink Throughput Measurement Dataset* (v20230917).
- Zenodo DOI: [10.5281/zenodo.10020034](https://doi.org/10.5281/zenodo.10020034)
- Record: https://zenodo.org/records/10020034
- License: [CC-BY-4.0](https://creativecommons.org/licenses/by/4.0/)

Paper:

- Pan, Jianping; Zhao, Jinwei; Cai, Lin. *Measuring a Low-Earth-Orbit Satellite Network*.
- IEEE PIMRC 2023. Preprint: https://arxiv.org/abs/2307.06863
- Paper DOI: [10.1109/PIMRC56721.2023.10294034](https://doi.org/10.1109/PIMRC56721.2023.10294034)

## What was measured (upstream README, not our claims)

- Victoria, BC Ethernet dish → Seattle PoP → GCP `us-west1-a`.
- Concurrent IRTT (UDP, 10 ms) + iPerf3 (TCP Cubic, `-R` downlink, 100 ms reports).
- 120 s sessions every 10 min, 2023-09-13 through 2023-09-17 UTC.
- Client and VM NTP via Google Public NTP.
- **SQM / CAKE: unknown.** Upstream README does not confirm SQM on this dump.
- Capacity column is **TCP Cubic downlink goodput**, not UDP saturation and not dish PHY / RF Mbps.
- Oracle = time-integral of that cubic-goodput series = **lower bound** on path capacity.

## Validity filter

- Complete IRTT + iperf3 JSON pair (identical filename timestamp). Indexed pairs: **716**.
- Duration ≥ 90 s on both IRTT `stats.duration` and iperf3 `end.sum_received.seconds`.
- Valid after filter: **716** (all indexed pairs passed on this dump).
- Not cherry-picks. Not a single session.

## Quantile rule (calendar, by session start time)

Sort valid sessions by UTC start timestamp parsed from the filename
(`YYYY-MM-DD-HH-MM-SS`, which matches iperf3 `start.timestamp` GMT).
Pick five nearest-rank indices at q ∈ {0, 0.25, 0.50, 0.75, 1.00}:

```
idx = min(n - 1, int(q * (n - 1) + 0.5))   # round-half-up
```

This is a **calendar** sample of the campaign, not a goodput-quantile sample.
We did **not** select by mean cubic goodput.

## Resample

- Replay grid `dt = 0.05` s.
- IRTT RTT: last non-lost sample with send-wall ≤ t (10 ms → 50 ms ZOH). Lost IRTT probes are skipped, not interpolated.
- iPerf3 cubic goodput: **hold-within-bin** of the 100 ms interval containing t (each 100 ms value covers two 50 ms slots).
- `capacity_mbps` == `cubic_goodput_mbps` by construction. Do not read this as dish PHY.
- `loss_p = 0` (IRTT UDP loss is not a labeled bottleneck-loss process for the TCP series).
- `reconfig = 0` always: **no invented handover flags** from TCP dips. Upstream dump does not label HOs.

## JSON fields used (inspected, not hypothesized)

- IRTT: `round_trips[].delay.rtt` (ns), `round_trips[].lost` (string), `round_trips[].timestamps.client.send.wall` (ns), `stats.duration` (ns).
- iPerf3: `intervals[].sum.bits_per_second`, `intervals[].sum.start`/`end`, `start.timestamp.timesecs`, `end.sum_received.seconds`, `end.sender_tcp_congestion` (cubic on all 716).

## Vendored sessions

| q | idx | session_id | start UTC | csv | overlap s | native IRTT p95 ms | native cubic-gp oracle Mbps |
|--:|----:|------------|-----------|-----|----------:|-------------------:|----------------------------:|
| q00 | 0 | `2023-09-13-00-40-00` | 2023-09-13T00:40:00Z | `q00_20230913T004000Z.csv` | 119.564 | 54.23 | 36.00 |
| q25 | 179 | `2023-09-14-06-30-00` | 2023-09-14T06:30:00Z | `q25_20230914T063000Z.csv` | 119.789 | 64.20 | 38.16 |
| q50 | 358 | `2023-09-15-12-20-00` | 2023-09-15T12:20:00Z | `q50_20230915T122000Z.csv` | 119.765 | 395.35 | 36.43 |
| q75 | 536 | `2023-09-16-18-00-00` | 2023-09-16T18:00:00Z | `q75_20230916T180000Z.csv` | 119.572 | 81.55 | 28.16 |
| q100 | 715 | `2023-09-17-23-50-00` | 2023-09-17T23:50:00Z | `q100_20230917T235000Z.csv` | 119.380 | 138.37 | 13.11 |

Source relative paths inside the decompressed dump:

- `2023-09-13-00-40-00`: `data/2023-09-13/irtt-10ms-2m-2023-09-13-00-40-00.json` + `data/2023-09-13/iperf3-2m-2023-09-13-00-40-00.json`
- `2023-09-14-06-30-00`: `data/2023-09-14/irtt-10ms-2m-2023-09-14-06-30-00.json` + `data/2023-09-14/iperf3-2m-2023-09-14-06-30-00.json`
- `2023-09-15-12-20-00`: `data/2023-09-15/irtt-10ms-2m-2023-09-15-12-20-00.json` + `data/2023-09-15/iperf3-2m-2023-09-15-12-20-00.json`
- `2023-09-16-18-00-00`: `data/2023-09-16/irtt-10ms-2m-2023-09-16-18-00-00.json` + `data/2023-09-16/iperf3-2m-2023-09-16-18-00-00.json`
- `2023-09-17-23-50-00`: `data/2023-09-17/irtt-10ms-2m-2023-09-17-23-50-00.json` + `data/2023-09-17/iperf3-2m-2023-09-17-23-50-00.json`

The ~1.17 GB `data-20230913-20230917.tar.zst` / ~9.7 GB `data/` tree is **not** vendored.

## Reproduce slices

```bash
curl -L -o /tmp/data-20230913-20230917.tar.zst \
  'https://zenodo.org/records/10020034/files/data-20230913-20230917.tar.zst?download=1'
mkdir -p /tmp/zhao_zenodo23/extract && tar -xf /tmp/data-20230913-20230917.tar.zst -C /tmp/zhao_zenodo23/extract
python -m experiments.zhao_zenodo23_ingest --extract-dir /tmp/zhao_zenodo23/extract
python -m experiments.zhao_zenodo23_geometry
```
