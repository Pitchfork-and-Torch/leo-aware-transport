# Next: ingest real Starlink CSV traces (successor product lock)

**Status:** stub. Not this PR's lock. `starlink_v1` is the **interim** product
path (v3.9 Crest ACCEPT on the synthetic generator). Measured Starlink
RTT/capacity traces are the north-star successor.

## Why

`starlink_v1` is a documented generative stand-in (cruise 40–75 ms, brief HO
spike, 40–150 Mbps). It is **not** a measurement. Occupancy, handover duration,
and capacity flicker on real dishes will differ. Re-lock CCA on CSVs before any
paid Optimizer claim that names Starlink.

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

cfg = LeoPathConfig(trace_csv="traces/starlink_real_seed13.csv", duration_s=90, dt_s=0.05)
run_sim(LeoAwareCCA, cfg=cfg)
```

OPE still applies (loss RNG orthogonal). Soft-QIR α stays 0.20 unless a new
era doc changes it.

## Ingest checklist (next loop)

1. **Source** — anonymized dish or PoP traces (RTT + bottleneck capacity or
   goodput proxy). Prefer ≥5 independent 90s windows to replace seeds
   13,7,42,99,123.
2. **Sanitize** — no user identifiers; resample to 10–50 ms slots; mark
   reconfig if a handover/beam event is known, else leave 0 and let endpoint
   detect.
3. **Land files** — `traces/real/YYYYMMDD-<id>.csv` plus a manifest
   (`traces/real/MANIFEST.md`) with collection date, duration, and license.
4. **Feasibility** — extend `walk_path_geometry` / `ope_feasibility` to CSV
   profiles; confirm oracle gp mean ≥ 75 and path p95 ≤ 138.8 **or** escalate
   a bar re-derivation (do not silently move 75/138.8).
5. **Lock** — `PRODUCT_PATH_PROFILE` becomes a CSV suite (or a flag
   `--path-profile starlink_csv`). Re-run CA/DLC/LSG on that era only.
   New archive tag. Do not mix `starlink_v1` generative numbers into that
   Current table.
6. **Keep** `ope_v36` as research; keep `starlink_v1` as the synthetic
   product stand-in until CSV lock ACCEPT.

## Out of scope here

- No real CSVs are vendored in this repository yet.
- Demo CSVs (`traces/starlink_v1_seed13.csv`, etc.) are **synthetic**.
- No paid landing bump on synthetic `starlink_v1` without an absolute lock,
  and even then the copy should say synthetic path until CSV lock.
