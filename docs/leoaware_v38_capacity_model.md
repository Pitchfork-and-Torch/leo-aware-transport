# LeoAware v3.8 capacity / HO realism (opt-in; not suite default)

**Date:** 2026-08-12  
**Status:** proposal for Jon. Default `path_profile="ope_v36"` is frozen.

Step 0 (`docs/leoaware_v38_step0_feasibility.md`) showed that absolute gp≥75 AND p95≤138.8 is **geometrically impossible** on the locked OPE generative path. This note specifies the opt-in models used to test whether a richer path would even *allow* those bars.

OPE (path identity across CCAs) is kept in every profile. Soft-QIR α stays 0.20.

## What is wrong with `ope_v36` as a Starlink stand-in

The v3.6/v3.7 generative path is a useful stress toy, not a Starlink capacity/HO model:

1. **Epoch-sticky RTT.** Each handover draws one RTT and holds it for ~12s. With `rtt_base=35ms + U(20,90)ms` and a 25% extra `+30–80ms`, a seed can sit at **~180 ms path RTT for an entire epoch** (seed 42 path p95 = 181.95 ms). Published Starlink measurements show typical RTT in a **~30–70 ms** band; handover disruption is **sub-second to ~1s**, not a 12s high-RTT satellite.
2. **Capacity band 20–120 Mbps uniform.** Mean ~70 Mbps, but unlucky seeds (123) average **45 Mbps** with **zero** time at ≥75 Mbps. Residential Starlink downlink is highly variable, but a 12s epoch stuck near the 20 Mbps floor is a harsh generator, not a measured occupancy distribution.
3. **Coupled-era 75/138.8** was BBR’s score on a *different orbit per CCA*. Under OPE, BBR is 58.21/152.89 because every CCA sees seed 123’s 45 Mbps path.

## Profiles

Set `LeoPathConfig.path_profile`. Suite / `multi_seed` / `run_suite` do **not** pass this field (default `ope_v36`).

### `starlink_rtt` — HO transient, same cap band

- Cruise RTT: `30ms + U(10,45)ms` → **40–75 ms**, 12% chance of `+10–25ms` (occasional ~50–100 ms satellite).
- HO spike: `U(20,55)ms` added **only** during `reconfig_loss_window_s` (0.4s), not the whole epoch.
- Capacity: still `U(20, 120) Mbps` (same band as ope_v36; RNG walk differs because RTT draws changed).

Feasibility (same 5 seeds, 90s): oracle gp mean **60.07** (still < 75); path p95 mean **70.79** (now < 138.8).

**Conclusion:** fixing RTT stickiness can make the p95 bar geometrically possible. It does **not** unlock gp≥75.

### `starlink_v1` — RTT + capacity band

Same RTT model as `starlink_rtt`, plus capacity `U(40, 150) Mbps` (constants `STARLINK_V1_CAP_MIN_BPS` / `MAX` in `leo_cc/network.py`).

Feasibility: oracle gp mean **84.03**; path p95 mean **70.79**. Absolute 75/138.8 is **geometrically possible**. This is **not** a CCA lock and **not** a product PASS.

Per-seed oracle gp: 13→98.97, 7→76.45, 42→82.77, 99→74.63, 123→87.34.

BBR’s ceiling also rises. If this profile becomes the default, Jon should decide whether 75/138.8 remains the product bar or should be re-derived vs BBR on the new path.

## CSV traces

```bash
python -m experiments.ope_feasibility --write-traces --profiles ope_v36,starlink_rtt,starlink_v1
```

| File | Profile |
|------|---------|
| `traces/ope_v36_seed13.csv` | frozen lock (demo) |
| `traces/starlink_rtt_seed13.csv` | RTT realism |
| `traces/starlink_v1_seed13.csv` | RTT + capacity |
| `traces/starlink_synthetic_seed13.csv` | pre-existing ope-style demo |

Replay: `LeoPathConfig(trace_csv=..., duration_s=90, dt_s=0.05)`. Real Starlink CSVs (same columns) are the preferred next lock if available.

## What this PR does not do

- Does not change `run_suite` / `multi_seed` defaults.
- Does not retune LeoAware CCA (no CA/DLC/LSG).
- Does not claim paid Optimizer breakthrough.
- Does not merge.

## Next if Jon picks `starlink_v1` (or real CSVs)

1. Flip default profile only after an explicit gate decision.
2. Re-baseline BBR + LeoAware 5-seed@90s on the new path (new era; do not mix with ope_v36 58/152 or coupled-era 75/138.8).
3. Then, and only then, chase CA → DLC → LSG against whatever bars Jon confirms.
4. Keep OPE and frozen soft-QIR α unless the new traces justify a documented α change.
