# LeoAware v3.8 capacity / HO realism

**Date:** 2026-08-12  
**Status (v3.8 Step 0):** proposal.  
**Status (v3.9):** Jon/Steward accepted option 1 — keep absolute 75/138.8 and make
**`starlink_v1` the product-lock path**. `ope_v36` stays the research relative-BBR
era. See `docs/harness_eras.md` and `docs/leoaware_v39_starlink_v1.md`.

Step 0 (`docs/leoaware_v38_step0_feasibility.md`) showed that absolute gp≥75 AND p95≤138.8 is **geometrically impossible** on the locked OPE generative path. This note specifies the models used to test whether a richer path would even *allow* those bars.

OPE (path identity across CCAs) is kept in every profile. Soft-QIR α stays 0.20.

## What is wrong with `ope_v36` as a Starlink stand-in

The v3.6/v3.7 generative path is a useful stress toy, not a Starlink capacity/HO model:

1. **Epoch-sticky RTT.** Each handover draws one RTT and holds it for ~12s. With `rtt_base=35ms + U(20,90)ms` and a 25% extra `+30–80ms`, a seed can sit at **~180 ms path RTT for an entire epoch** (seed 42 path p95 = 181.95 ms). Published Starlink measurements show typical RTT in a **~30–70 ms** band; handover disruption is **sub-second to ~1s**, not a 12s high-RTT satellite.
2. **Capacity band 20–120 Mbps uniform.** Mean ~70 Mbps, but unlucky seeds (123) average **45 Mbps** with **zero** time at ≥75 Mbps. Residential Starlink downlink is highly variable, but a 12s epoch stuck near the 20 Mbps floor is a harsh generator, not a measured occupancy distribution.
3. **Coupled-era 75/138.8** was BBR’s score on a *different orbit per CCA*. Under OPE, BBR is 58.21/152.89 because every CCA sees seed 123’s 45 Mbps path.

## Profiles

Set `LeoPathConfig.path_profile`. Generative default remains `ope_v36` (frozen
research identity). **Product harnesses** (`multi_seed`, `run_suite`,
`run_ablation`) default to **`starlink_v1`**.

### `starlink_rtt` — HO transient, same cap band

- Cruise RTT: `30ms + U(10,45)ms` → **40–75 ms**, 12% chance of `+10–25ms` (occasional ~50–100 ms satellite).
- HO spike: `U(20,55)ms` added **only** during `reconfig_loss_window_s` (0.4s), not the whole epoch.
- Capacity: still `U(20, 120) Mbps` (same band as ope_v36; RNG walk differs because RTT draws changed).

Feasibility (same 5 seeds, 90s): oracle gp mean **60.07** (still < 75); path p95 mean **70.79** (now < 138.8).

**Conclusion:** fixing RTT stickiness can make the p95 bar geometrically possible. It does **not** unlock gp≥75.

### `starlink_v1` — RTT + capacity band

Same RTT model as `starlink_rtt`, plus capacity `U(40, 150) Mbps` (constants `STARLINK_V1_CAP_MIN_BPS` / `MAX` in `leo_cc/network.py`).

Feasibility: oracle gp mean **84.03**; path p95 mean **70.79**. Absolute 75/138.8 is **geometrically possible**.

Per-seed oracle gp: 13→98.97, 7→76.45, 42→82.77, 99→74.63, 123→87.34.

v3.9: this profile **is** the product-lock path. Bars stay absolute 75/138.8
(not re-derived vs BBR). CCA chase is CA → DLC → LSG on this era only. Do not
mix `ope_v36` 58/152 or coupled-era Tide numbers into a `starlink_v1` Current
table. Real CSVs are next (`docs/starlink_csv_ingest.md`).

## CSV traces

```bash
python -m experiments.ope_feasibility --write-traces --profiles ope_v36,starlink_rtt,starlink_v1
```

| File | Profile |
|------|---------|
| `traces/ope_v36_seed13.csv` | frozen research path (demo) |
| `traces/starlink_rtt_seed13.csv` | RTT realism |
| `traces/starlink_v1_seed13.csv` | product-lock generative demo |
| `traces/starlink_synthetic_seed13.csv` | pre-existing ope-style demo |

Replay: `LeoPathConfig(trace_csv=..., duration_s=90, dt_s=0.05)`. Real Starlink CSVs (same columns) are the successor product lock — `docs/starlink_csv_ingest.md`.

## v3.9 era switch (done)

1. Product default is `starlink_v1` (`leo_cc/harness.py`).
2. Re-baseline BBR + LeoAware 5-seed@90s on that path (new era).
3. CA → DLC → LSG against absolute 75/138.8.
4. OPE + frozen soft-QIR α=0.20 kept.
5. No paid OrbitStack landing bump without an absolute lock.
