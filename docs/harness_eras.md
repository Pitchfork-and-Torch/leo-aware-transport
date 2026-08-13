# Harness eras (do not mix in Current)

OrbitStack evaluates LeoAware on more than one generative path. **Never put
numbers from different eras in the same Current hero table.**

| Era | Profile | Dual-gate | Role |
|-----|---------|-----------|------|
| Coupled-RNG (historical) | pre-OPE `path.rng` shared with loss | absolute 75/138.8 on a *different orbit per CCA* | v3.4-p95 / v3.5 Tide. Not comparable to OPE. |
| `ope_v36` research | frozen v3.6/v3.7 generative path | **relative to BBR** on the same orbit | Science lock. Absolute 75/138.8 **impossible** (oracle gp 60.48, path p95 142.32). |
| **`starlink_v1` product** | cruise RTT 40–75 ms; HO spike in the 0.4s loss window; cap 40–150 Mbps | **absolute gp≥75 AND p95≤138.8** | **v3.9 product-lock default** (`multi_seed` / `run_suite`). |
| Real Starlink CSV (next) | measured RTT/capacity traces | same absolute bars unless re-derived | Successor lock. Stub: `docs/starlink_csv_ingest.md`. |

## Defaults

| Surface | Default | Override |
|---------|---------|----------|
| `LeoPathConfig.path_profile` | `ope_v36` (frozen research identity) | pass `path_profile=` |
| `python -m experiments.multi_seed` | **`starlink_v1`** | `--path-profile ope_v36` |
| `python -m experiments.run_suite` | **`starlink_v1`** | `--path-profile ope_v36` |
| `python -m experiments.run_ablation` | **`starlink_v1`** | `--path-profile ope_v36` |

Constants: `leo_cc/harness.py` (`PRODUCT_PATH_PROFILE`, `RESEARCH_PATH_PROFILE`, bars).

Soft-QIR **α is frozen at 0.20** / 25 ms cap in every era (`leo_cc/sim.py`).
`p95(rtt − path_base)` is a **secondary** queue diagnostic. It does not replace
absolute ACK p95.

## Product bars (starlink_v1 era)

Multi-seed endpoint `leo_fast_ho` seeds **13,7,42,99,123** @ 90s:

| Gate | Bar |
|------|-----|
| gp mean | ≥ 75.0 Mbps |
| p95 mean | ≤ 138.8 ms |
| terrestrial gp | ≥ 77 Mbps (note soft-QIR p95; path 40 ms + sojourn) |
| integrity | ASCENT-D + OPE green |

ACCEPT only if all gates pass. Else REJECT/WIP honest Pareto — **do not redefine bars**.

v3.9 Crest scorecard (not Current, no paid bump): LeoAware means gp **82.07** /
p95 **76.26** / terr **78.62** on `starlink_v1`. Geometry 84.03 / 70.79. Archive
`results/archive/20260812-v39-starlink-v1/`. **Current remains v3.7 OCE** on
`ope_v36` (58.78 / 152.1) until Jon merges.

## Why two generative defaults

`LeoPathConfig` keeps `ope_v36` so research geometry cannot silently drift
(golden first-HO on seed 13). Product scripts **explicitly** select `starlink_v1`.
That is the era switch, not a silent retune of the OPE path.
