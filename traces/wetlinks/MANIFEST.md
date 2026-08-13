# WetLinks 90s windows (`wetlinks_v1`)

Five hold-expanded slices from [sys-uos/WetLinks](https://github.com/sys-uos/WetLinks)
(Laniewski et al., TMA 2024). License: [CC BY-SA 4.0](https://creativecommons.org/licenses/by-sa/4.0/).

These are **not** dish PHY traces and **not** a continuous 90s 50 ms path.
WetLinks `net_iperf` is a 15 s UDP run every ~3 min; `net_ping` is a ~49 s /
250-packet aggregate (avg / worst / best / std / loss). Replay files use the
existing LeoPath columns `t_s,rtt_ms,capacity_mbps,loss_p,reconfig`.

## Citation

D. Laniewski, E. Lanfer, B. Meijerink, R. van Rijswijk-Deij, N. Aschenbruck,
"WetLinks: a Large-Scale Longitudinal Starlink Dataset with Contiguous Weather
Data", Proc. of the 8th Network Traffic Measurement and Analysis Conf. (TMA), 2024.
https://arxiv.org/abs/2402.16448

## How the five windows were chosen

Deterministic calendar quantiles after a validity filter
(`capacity > 1 Mbps`, `5 < ping_avg < 500 ms`). **Not** cherry-picked for
goodput or p95.

| id | site | source start (UTC-naive, as published) | iperf mean Mbps | ping avg / worst / best ms | loss |
|----|------|----------------------------------------|----------------:|---------------------------:|-----:|
| `w1_enschede_20231110T091227` | Enschede | 2023-11-10 09:12:27 | 396.17 | 58.73 / 84.29 / 47.95 | 0% |
| `w2_enschede_20240215T153911` | Enschede | 2024-02-15 15:39:11 | 406.70 | 52.10 / 105.08 / 43.66 | 0.40% |
| `w3_osnabruck_20230930T061825` | Osnabrück | 2023-09-30 06:18:25 | 66.02 | 68.24 / 94.14 / 56.45 | 0% |
| `w4_osnabruck_20231220T160942` | Osnabrück | 2023-12-20 16:09:42 | 193.42 | 64.86 / 109.87 / 48.12 | 0% |
| `w5_osnabruck_20240223T171843` | Osnabrück | 2024-02-23 17:18:43 | 164.23 | 59.95 / 83.79 / 47.72 | 0.40% |

Reproduce:

```bash
python3 -m experiments.slice_wetlinks --fetch
```

## Inferences (read before quoting numbers)

1. **`capacity_mbps`** = UDP iperf **download mean** (15 s), held for 90 s.
   Saturated-flow goodput proxy. Not a Starlink dish PHY rate.
2. **`rtt_ms`** = `ping_avg` held. If `ping_worst - ping_avg ≥ 20 ms`, one
   0.4 s spike to `ping_worst` is placed at **t = 12.0 s**. Spike *timing* is
   inferred: WetLinks does not publish per-packet ping times.
3. **`loss_p`** = `ping_packet_loss / 100` (aggregate). Not a per-slot series.
4. **`reconfig`** = 1 on the first slot of that inferred spike. Not a dish
   handover log.
5. **Not done:** generative HO cadence, `starlink_v2` flicker, invented 1 s
   ping series, empty `traces/real/` scaffold.

Measured coverage per window is **15 s iperf + one ping aggregate**. The
remaining 75 s is hold.

## Geometry (no CCA)

`python3 -m experiments.run_wetlinks --geometry-only`

| window | oracle gp Mbps | path p95 ms | path max ms |
|--------|---------------:|------------:|------------:|
| w1 | 396.17 | 58.73 | 84.29 |
| w2 | 405.07 | 52.10 | 105.08 |
| w3 | 66.02 | 68.24 | 94.14 |
| w4 | 193.42 | 64.86 | 109.87 |
| w5 | 163.58 | 59.95 | 83.79 |
| **mean** | **244.85** | **60.78** | — |

Absolute bars (gp mean ≥ 75 AND p95 mean ≤ 138.8): **geometry PASS**.
Window w3's oracle (66.02) is below 75 — that is a real low-cap cycle, not a
bug. The gate is the **five-window mean**.

Path p95 of the replay series equals `ping_avg` because a 0.4 s spike does
not move p95 of 1800 slots. Source `ping_worst` is `path_max`.

## Era

`wetlinks_v1`. Do **not** mix with synthetic `starlink_v1` 82.09/76.26 or
`ope_v36` 58/152. Product CCA on synthetic `starlink_v1` remains v3.9 Crest.
