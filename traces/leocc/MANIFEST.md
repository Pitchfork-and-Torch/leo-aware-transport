# leocc_v1 — vendored LeoCC downlink replay slices

Research-era Starlink access traces. **Not** a product lock. **Do not merge**
into Current / paid copy. **Do not mix** with `wetlinks_v1`, `zhao_zenodo23`,
or synthetic `starlink_v1` FillGap 82.45/76.26 (prior Crest 82.07/76.26).

## Citation (required)

- Lai, Zeqi; Li, Zonglun; Wu, Qian; Li, Hewu; Li, Jihao; Xie, Xin; Li, Yuanjie; Liu, Jun; Wu, Jianping.
  *LeoCC: Making Internet Congestion Control Robust to LEO Satellite Dynamics*.
  ACM SIGCOMM 2025. DOI [10.1145/3718958.3750491](https://doi.org/10.1145/3718958.3750491).
- Code + recorder: https://github.com/SpaceNetLab/LeoCC (MIT).
- Traces: Tsinghua Cloud share https://cloud.tsinghua.edu.cn/d/9fc6fd096e764f57bd25/ (`4.8K.zip`).

## What was measured (upstream, not our claims)

- Concurrent **heavy UDP** (iperf3 saturation) + **light ICMP** ping.
- Each trace ~120 s. Four anonymous sites (A–D) × uplink/downlink × 600.
- `bw_*.txt`: mahimahi timestamps; each repeated line = 12 Mbps at that millisecond.
- `delay_*.txt`: one-way delay (ms) per 10 ms bin (LeoReplayer / traces README).
- Capacity is **UDP saturation**, not TCP Cubic goodput, not dish PHY / RF Mbps.
- ICMP rides a separate Starlink SQM queue (LeoReplayer README). Delay is **base**
  path delay, not CCA-queued RTT. Soft-QIR still adds sojourn in our sim.

## Direction filter (stated before looking at gp/p95)

This era slices **downlink only** (4×600 = 2400), matching WetLinks download
and Zhao `-R` downlink. Uplink dirs are present in the zip (counted below)
and are a different bottleneck class (LeoReplayer: higher uplink loss,
lower sat rate). We do **not** mix them into the five-window mean.

## Validity filter

- Downlink pair `bw_N.txt` + `delay_N.txt` exists in the zip. Indexed: **2400**.
- Delay bins ≥ 9000 (native duration ≥ 90 s).
- At least one positive 1 ms UDP-sat sample in [0, 90 s).
- Valid after filter: **2398**.
- Excluded short delay (not gp/p95): `D/16` (75.92 s), `D/212` (88.39 s) on this dump.
- Not cherry-picks. Not a single pretty session.

## Quantile rule (catalog order, not goodput)

Sort valid downlink traces by `(site A..D, trace_no 1..600)`.
Nearest-rank q ∈ {0, 0.25, 0.50, 0.75, 1.00}:

```
idx = min(n - 1, int(q * (n - 1) + 0.5))   # round-half-up
```

We did **not** select by mean UDP-sat or delay p95.

## Resample / inferences

- Gate window: first **90 s** of each ~120 s trace (product duration).
- Replay grid `dt = 0.05` s.
- OWD: last-obs of the 10 ms delay bin with start ≤ t.
  Source 0 is replaced by the last positive OWD (do not invent a floor).
- **`rtt_ms = 2 × owd_ms`**. traces/README + mahimahi `mm-delay` are one-way;
  a packet sees the delay on both directions. Native OWD p95 is also archived.
- Capacity: mean of the 50 one-millisecond UDP-sat samples in the slot.
- `loss_p = 0.0001` (LeoReplayer empirical downlink). Not a HO series.
- `reconfig = 0` always: **no invented handover flags**. Their extract script
  is documented as unreliable on irregular traces; we do not run it.

## Vendored windows

| q | idx | site | trace | csv | native OWD p95 ms | 2×OWD p95 ms | native UDP-sat oracle Mbps |
|--:|----:|------|------:|------|------------------:|-------------:|---------------------------:|
| q00 | 0 | A | 1 | `q00_A_downlink_001.csv` | 16.00 | 32.00 | 425.83 |
| q25 | 599 | A | 600 | `q25_A_downlink_600.csv` | 16.00 | 32.00 | 353.33 |
| q50 | 1199 | B | 600 | `q50_B_downlink_600.csv` | 30.00 | 60.00 | 408.26 |
| q75 | 1798 | C | 599 | `q75_C_downlink_599.csv` | 54.00 | 108.00 | 406.40 |
| q100 | 2397 | D | 600 | `q100_D_downlink_600.csv` | 97.00 | 194.00 | 380.91 |

Zip members:

- `q00`: `Anonymous_A_downlink/1/bw_1.txt` + `Anonymous_A_downlink/1/delay_1.txt`
- `q25`: `Anonymous_A_downlink/600/bw_600.txt` + `Anonymous_A_downlink/600/delay_600.txt`
- `q50`: `Anonymous_B_downlink/600/bw_600.txt` + `Anonymous_B_downlink/600/delay_600.txt`
- `q75`: `Anonymous_C_downlink/599/bw_599.txt` + `Anonymous_C_downlink/599/delay_599.txt`
- `q100`: `Anonymous_D_downlink/600/bw_600.txt` + `Anonymous_D_downlink/600/delay_600.txt`

The ~699 MB `4.8K.zip` / 4800-trace tree is **not** vendored.

## Reproduce slices

```bash
curl -L -o /tmp/leocc/4.8K.zip 'https://cloud.tsinghua.edu.cn/d/9fc6fd096e764f57bd25/files/?p=/4.8K.zip&dl=1'
python -m experiments.slice_leocc --zip /tmp/leocc/4.8K.zip
python -m experiments.run_leocc --geometry-only
```

