# v3.11 WetLinks CSV lock

**Era:** `wetlinks_v1`  
**CCA:** v3.9 Crest defaults (endpoint-only). No Halo / QSP / PATHHINT.  
**Not Current. No paid bump.** Soft-QIR α frozen 0.20.

## Hypothesis

A small, cited WetLinks slice (5×90 s in the existing CSV contract) is
enough to say whether the absolute bars (gp mean ≥ 75 AND p95 mean ≤ 138.8)
are geometrically possible on a **measured** Starlink path — before any CCA
invention.

## What shipped

- `traces/wetlinks/*.csv` — five windows, columns
  `t_s,rtt_ms,capacity_mbps,loss_p,reconfig`
- `traces/wetlinks/MANIFEST.md` — source, license, inferences
- `experiments/slice_wetlinks.py` — re-fetch + deterministic quantile picks
- `experiments/run_wetlinks.py` — geometry first, then Crest / BBR / CUBIC
- `experiments/test_wetlinks_integrity.py`

Source: [sys-uos/WetLinks](https://github.com/sys-uos/WetLinks)
(Laniewski et al., TMA 2024, CC BY-SA 4.0). `net_iperf` download mean →
`capacity_mbps`. `net_ping` avg → `rtt_ms`. One inferred reconfig when
`ping_worst - ping_avg ≥ 20 ms` (0.4 s spike at t=12.0; timing inferred).

## Geometry (no CCA)

| | oracle gp mean | path p95 mean |
|--|---------------:|--------------:|
| 5 windows | **244.85** | **60.78** |

Bars possible: **yes**. w3 oracle 66.02 Mbps is a real low-cap Osnabrück
cycle; the gate is the mean. Path p95 equals `ping_avg` (a 0.4 s spike does
not move p95 of 1800 slots). `path_max` is source `ping_worst`.

**Inferences that inflate oracle gp:** the 15 s UDP iperf mean is held for
90 s. WetLinks has no continuous 90 s capacity series (median gap ~3 min).

## CCA

Run only after geometry PASS:

```bash
python3 -m experiments.run_wetlinks --tag 20260813-v311-wetlinks
```

ACCEPT on this era only if Crest clears gp≥75 AND p95≤138.8 on the five
windows **and** terr ≥77 on the synthetic terrestrial control. Else honest
REJECT. Do not mix the table with `starlink_v1` 82.09/76.26.

## What this is not

- Not a product-lock replacement for synthetic `starlink_v1`
- Not dish/RF Mbps
- Not PATHHINT / Halo / QSP
- Not an empty `traces/real/` scaffold
