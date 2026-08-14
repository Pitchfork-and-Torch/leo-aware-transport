# Real Starlink CSV ingest (`wetlinks_v1` first lock)

**Status:** v3.11 WetLinks CSV lock. Five 90 s windows are vendored under
`traces/wetlinks/`. Do **not** ship an empty `traces/real/` scaffold.
`starlink_v1` remains the **synthetic** product path (v3.9 Crest). Measured
CSV replay is a **new era** — never mix with `starlink_v1` 82.09/76.26 or
`ope_v36` 58/152.

## Source (this lock)

[sys-uos/WetLinks](https://github.com/sys-uos/WetLinks) — Laniewski et al.,
TMA 2024, CC BY-SA 4.0. Two EU dishes (Osnabrück, Enschede), ~6 months.
This repo vendors **small slices only**: `net_iperf` 15 s UDP means +
`net_ping` aggregates, hold-expanded to the existing LeoPath columns.

Raw LENS dumps and full `net_iperf.csv` (~80–100 MB/site) are **not**
vendored. Re-slice:

```bash
python3 -m experiments.slice_wetlinks --fetch
python3 -m experiments.run_wetlinks --geometry-only
python3 -m experiments.run_wetlinks --tag 20260813-v311-wetlinks
```

If GitHub download is blocked, **STOP**. Do not invent traces or fall back
to `starlink_v2`.

Manifest + inferences: `traces/wetlinks/MANIFEST.md`.
Design: `docs/leoaware_v311_wetlinks.md`.

## Why WetLinks is sparse

| Stream | Cadence | What we get |
|--------|---------|-------------|
| `net_iperf` | 15 s UDP run every ~3 min | 1 s samples internally; we use the 15 s **download mean** |
| `net_ping` | ~49 s / 250 packets after iperf | avg / worst / best / std / loss — **not** a per-packet series |

A true 90 s 50 ms RTT+capacity path does **not** exist in WetLinks. The
replay hold-expands one cycle and marks one inferred RTT jump. That is
documented, not hidden.

## CSV contract (already implemented)

`leo_cc.network.load_trace_csv` / `LeoPathConfig(trace_csv=...)`:

```csv
t_s,rtt_ms,capacity_mbps,loss_p,reconfig
0.00,42.1,95.0,0.0005,0
12.05,88.0,61.2,0.08,1
```

Required: time, RTT, capacity. Optional: `loss_p`, `reconfig` (0/1).
See `docs/traces_and_ascent.md`.

Replay:

```python
from leo_cc.network import LeoPathConfig
from leo_cc.sim import run_sim
from leo_cc.ccas import LeoAwareCCA

cfg = LeoPathConfig(
    trace_csv="traces/wetlinks/w1_enschede_20231110T091227.csv",
    duration_s=90,
    dt_s=0.05,
    path_profile="wetlinks_v1",
)
run_sim(LeoAwareCCA, cfg=cfg)
```

OPE still applies (loss RNG orthogonal). Soft-QIR α stays 0.20 unless a new
era doc changes it.

## Geometry first (hard order)

Bars stay gp mean ≥ 75 AND p95 mean ≤ 138.8. If either fails on the five
windows → **STOP**, report windows, no CCA, no quiet rebaseline.

v3.11 geometry (hold-expanded slices): oracle gp mean **244.85**, path p95
mean **60.78**. Window w3 oracle **66.02** is below 75 (real low-cap cycle);
the gate is the five-window mean. **Geometry PASS.**

CCA (Crest, `dt=0.01`): gp **156.70** / p95 **63.98** / terr **78.62**.
**ACCEPT `wetlinks_v1` only** — not Current, not a `starlink_v1` replacement.
250 KB buffer caps send at ~200 Mbps (w1/w2 sit there).

Uncap cook (1 MB, same windows): Crest **239.72/70.38** vs BBR **240.48/71.38**.
**REJECT** (Crest gp < BBR). Footnote the 156.70 table; do not mix.
See `docs/leoaware_v311_wetlinks_uncap.md`.

## Era rules

- Label: `wetlinks_v1`.
- Product CCA on synthetic `starlink_v1` stays **v3.9 Crest**.
- `PRODUCT_PATH_PROFILE` stays `starlink_v1`.
- No Halo / QSP / default-on PATHHINT freeze.
- No dish/RF Mbps claims. Capacity here is UDP iperf download.

## Still out of scope

- Demo CSVs (`traces/starlink_v1_seed13.csv`, etc.) remain **synthetic**.
- No paid landing bump on synthetic `starlink_v1`.
- No empty `traces/real/` directory.

## Successor research ingest (`leocc_v1`, v3.13)

[SpaceNetLab/LeoCC](https://github.com/SpaceNetLab/LeoCC) (Lai et al., SIGCOMM
2025, MIT) publishes concurrent **heavy UDP saturation + ICMP OWD** traces
(~120 s, 4.8K). That is the first public dump that is actually continuous
≥90 s UDP-sat + delay — WetLinks is 15 s hold-expand; zhao_zenodo23 is TCP
Cubic (PR #12, p95 FAIL, not for dual-gate ACCEPT).

Vendored slices: `traces/leocc/`. Design: `docs/leoaware_v313_leocc.md`.
**Not** a product-lock replacement. Do not mix with `wetlinks_v1` 239.72/70.38
or `starlink_v1` Crest 82.09/76.26.
