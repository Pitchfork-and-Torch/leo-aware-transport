# LeoAware v3.10 Halo — REJECT (starlink_v1)

**Date:** 2026-08-13  
**Branch:** `cursor/v310-halo-84b8`  
**Decision:** **REJECT** for product CCA. v3.9 Crest stayed the starlink_v1 Accept
of that cook. **Current is now v3.17 FillGap** (82.45 / 76.26); Crest is the prior lock.  
**This cook is not Current.**

## Goal

Clear BBR on synthetic `starlink_v1` multi-seed means (or close the ~2 Mbps
oracle gap) while holding absolute dual-gate gp≥75 / p95≤138.8.

v3.9 Crest baseline: LeoAware **82.07 / 76.26** vs BBR **82.44 / 76.66**.

## Levers tried (endpoint-only)

| Lever | Result vs Crest |
|-------|-----------------|
| EpochMemory soft-seed + HO-PLL + SSE 1.45× | **81.99** gp — regress |
| Cruise Capacity Halo (CCH) max-filter | **81.88** — regress |
| Orbit Pulse (BBR-like 8-RTT probe) | **82.04** — flat/slight regress |
| Softer REPROBE cut 0.62–0.70 | no gain; 0.66+ hurts seed 13 |
| Clean-cruise p90 lift | **82.07** — flat |
| CFR/CRE (fade/rise echo) | ≈ Crest; no BBR clear |

Ablation (90s `leo_fast_ho`, seeds 13,7,42,99,123):

| Variant | gp mean | p95 mean | Δ vs BBR |
|---------|--------:|---------:|---------:|
| BBR | 82.439 | 76.664 | — |
| Crest (halo=0, pulse=0) | **82.089** | 76.264 | −0.35 |
| Pulse only | 82.037 | 76.264 | −0.40 |
| Memory only | 81.876 | 76.264 | −0.56 |
| Memory + Pulse | 82.076 | 76.264 | −0.36 |

## Why

On sticky-capacity `starlink_v1`, LeoAware is already ~97.7% of oracle. The
residual vs BBR is BBR’s max-filter + no hop invalidation tracking the same
orbit slightly fuller. Stretch / memory / pulse theater does not buy a clear
Pareto; it mostly taxes reclaim.

**Do not ship +0.0–0.1 “wins” or regressions as Optimizer breakthroughs.**

## Defaults

`use_halo=False`, `use_orbit_pulse=False`, `use_cfr=False`. Product CCA path
remains **v3.9 Crest**. Flags kept for ablation only.

## Archive

Halo WIP multi-seed (SSE era): `results/archive/20260813-v310-halo/` (absolute
bars still PASS; research reject vs Crest/BBR).

## Next

1. Real Starlink CSV lock (`docs/starlink_csv_ingest.md`) — preferred.
2. Opt-in `starlink_v2` mid-epoch flicker research (`docs/leoaware_v310_starlink_v2.md`)
   — not a product lock; first probe still has Leo behind BBR.
3. Do not bump Current / paid copy without a clear multi-seed Pareto or a new
   Jon-gated path era.
