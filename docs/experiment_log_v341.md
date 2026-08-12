## v3.4.1 overnight - milder delay_yield (gp floor 75 still miss) - REJECT/WIP

**Date:** 2026-08-12  
**Branch:** `pr-p95-reclaim-v341` (from tip `8442b1c`)  
**Hypothesis:** From locked v3.4-p95 (73.57 / 138.37), a large ablatable micro-sweep can reclaim ≥75 gp while keeping p95 ≤ 138.8 without DTCE.

### Sweep honesty

Tried (and **rejected**) many levers stacked on v3.4: fill ceilings, max-filter gates, detect cooldown/threshold, cruise targets, post-cut cwnd floors, longer REPROBE phases, streak-gated caps, sizing-RTT mixes. Most destroyed multi-seed Pareto. Notable negatives: detect tighten (seed 42 collapse), fill 1.58 (seed 42 collapse), cruise step 0.95 (broad collapse).

**Ablation winner (only clear Pareto win vs tip):** mild delay_yield subtract `0.35 → 0.25` MSS at `delay_ratio > 1.45`.

### Code (`leo_cc/leo_aware.py` + `leo_cc/ccas.py` re-export; hybrid fuse rails unchanged)

- Mild yield subtract 0.25 MSS (was 0.35)
- Suite default still endpoint-only; no DTCE / EpochMemory
- LeoAwareCCA source shipped as `leo_aware.py.z64.[0-3]` + thin loader (MCP size limits)

### Multi-seed endpoint (90s, seeds 13,7,42,99,123) - locked — tag `20260812-p95-reclaim-v341`

| CCA | gp mean | p95 mean | vs BBR (70.88 / 138.8) |
|-----|--------:|---------:|------------------------|
| CUBIC | 5.47 | 124.8 | collapse |
| BBRv3approx | 70.88 | 138.8 | reference |
| LeoAware v3.4-p95 (tip) | 73.57 | 138.37 | p95 gate / gp floor miss |
| **LeoAware v3.4.1** | **73.92** | **128.15** | **p95 PASS; gp floor still miss** |
| LeoAware v3.3-A | 78.06 | 149.7 | historical gp peak |

Per-seed LeoAware `leo_fast_ho`:

| seed | gp | p95 |
|-----:|---:|----:|
| 13 | 77.05 | 165.4 |
| 7 | 83.54 | 111.1 |
| 42 | 80.77 | 103.8 |
| 99 | 65.54 | 149.5 |
| 123 | 62.71 | 111.0 |

### Other scenarios

| Scenario | LeoAware gp | p95 | note |
|----------|------------:|----:|------|
| leo_single | 62.65 | 160.5 | unchanged vs v3.4 |
| terrestrial | **78.20** | 40.0 | ≥ 77 @ 40 ms **PASS** |

### Integrity

| Check | Result |
|-------|--------|
| `test_ascent_d_integrity` | **PASS** |
| Suite default | endpoint-only |
| Hybrid fuse rails | unchanged |

Archive: `results/archive/20260812-p95-reclaim-v341/`

### Gate scorecard (overnight session bar)

| Check | Bar | Result |
|-------|-----|--------|
| gp mean | ≥ 75.0 | **73.92 FAIL** (~1.08 Mbps short; still > BBR) |
| p95 mean | ≤ 138.8 | **128.15 PASS** (large headroom vs tip) |
| terrestrial | ≥ 77 @ 40 | **78.20 PASS** |
| integrity | green | PASS |

**Decision: REJECT / WIP vs accept bar (gp≥75).**  
Honest Pareto improvement over tip (gp +0.35, p95 −10.2) but product floor 75 not cleared. Seeds 99/123 remain the gp drag; small fill/detect/cruise levers could not lift them without collapsing other seeds. Open draft PR with numbers; do not market as ≥75 gp.

---
