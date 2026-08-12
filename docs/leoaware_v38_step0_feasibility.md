# LeoAware v3.8 Step 0: absolute dual-gate feasibility (OPE era)

**Date:** 2026-08-12  
**Branch:** `cursor/v38-step0-feasibility-586b`  
**Tip:** `5652fa0` (v3.7 OCE)  
**Decision:** **REJECT / WIP** for product absolute dual-gate. **STOP CCA theater.** Escalate path/HO realism to Jon.

This is not a Current-tab bump. Paid OrbitStack copy must not change.

## Product bars (unchanged; no goalpost move)

Multi-seed endpoint `leo_fast_ho` seeds **13,7,42,99,123** (90s):

| Gate | Bar |
|------|-----|
| gp mean | ≥ 75.0 Mbps |
| p95 mean | ≤ 138.8 ms |
| terrestrial gp | ≥ 77 Mbps (soft-QIR p95 noted honestly) |
| integrity | ASCENT-D + OPE green |

Relative “≈ BBR at ~58 gp” is **research-only**, not a product PASS.

Coupled-era Tide 76.27/147.39 and v3.4 73.57/138.37 used **CCA-coupled path RNG**. They are a different physics era and must not be mixed into an OPE Current hero.

## Step 0 method

1. **Keep OPE** — `loss_rng = Random(seed ^ 0x10CC)` remains orthogonal to `path.rng`. Same seed ⇒ identical HO/RTT/cap timeline across CCAs.
2. **Freeze soft-QIR α** — `SOFT_QIR_ALPHA = 0.20`, `SOFT_QIR_CAP_S = 0.025` in `leo_cc/sim.py`. Do not retune α as a p95 lever.
3. **Secondary diagnostic** `p95(rtt − path_base)` on ACK samples. Does **not** replace the absolute ACK p95 product gate.
4. **Oracle goodput** — time-integral of `capacity × (1 − loss_p)`. This is the drain-and-survive ceiling if the pipe is always full. No CCA can beat it on this path.

Reproduce:

```bash
python -m experiments.test_ascent_d_integrity
python -m experiments.ope_feasibility --with-cca --tag 20260812-v38-step0
```

Archive: `results/archive/20260812-v38-step0/`

## Frozen OPE geometry (`path_profile=ope_v36`, suite default)

Time-weighted path (no CCA), 90s `leo_fast_ho`:

| seed | n_ho | mean cap | oracle gp | path p50 | path p95 | cap-weighted p95 | max RTT | frac cap≥75 |
|-----:|-----:|---------:|----------:|---------:|---------:|-----------------:|--------:|------------:|
| 13 | 7 | 70.33 | 70.11 | 112.4 | 141.38 | 141.38 | 141.38 | 0.38 |
| 7 | 7 | 57.95 | 57.77 | 82.8 | 135.97 | 135.97 | 135.97 | 0.29 |
| 42 | 7 | 53.44 | 53.29 | 65.9 | 181.95 | 181.95 | 181.95 | 0.23 |
| 99 | 7 | 76.72 | 76.49 | 83.2 | 121.28 | 121.28 | 121.28 | 0.53 |
| 123 | 6 | 44.86 | 44.75 | 59.9 | 131.00 | 131.00 | 131.00 | 0.00 |
| **mean** | | **60.66** | **60.48** | | **142.32** | **142.32** | | |

### Why gp ≥ 75 is impossible

Oracle mean **60.48 Mbps**. Target 75 is **+14.5 Mbps above the physical ceiling**. Seed 123’s entire orbit averages 44.9 Mbps (frac≥75 = 0). No sender algorithm can deliver 75 mean on this generative path.

### Why p95 ≤ 138.8 is impossible

Path-base p95 mean **142.32 ms** with **zero queue**. Capacity-weighted p95 (full-pipe ACK mix) is the same 142.32, so sending more or less during high-RTT epochs does not change the mix enough to matter. Seed 42’s path p95 is **181.95 ms** for a whole ~12s epoch. Soft-QIR only adds more.

Even α = 0 (illegal here; α is frozen) would leave ACK p95 ≈ 142.3 > 138.8.

## CCA probe (confirms path domination, not a new lock)

Same seeds, endpoint-only, frozen α=0.20. Excess = ACK RTT − path_base.

| seed | BBR gp | Leo gp | oracle | Leo / oracle | BBR p95 | Leo p95 | path p95 | Leo p95 excess |
|-----:|-------:|-------:|-------:|-------------:|--------:|--------:|---------:|---------------:|
| 13 | 68.18 | 67.19 | 70.11 | 95.8% | 153.38 | 153.38 | 141.38 | 12.0 |
| 7 | 56.12 | 56.40 | 57.77 | 97.6% | 151.97 | 145.97 | 135.97 | 16.0 |
| 42 | 48.67 | 51.69 | 53.29 | 97.0% | 183.95 | 185.95 | 181.95 | 14.0 |
| 99 | 74.31 | 74.85 | 76.49 | 97.9% | 126.14 | 126.14 | 121.28 | 8.0 |
| 123 | 43.77 | 43.76 | 44.75 | 97.8% | 149.00 | 149.00 | 131.00 | 18.0 |
| **mean** | **58.21** | **58.78** | **60.48** | **97.2%** | **152.89** | **152.09** | **142.32** | **13.6** |

LeoAware v3.7 is already at **~97% of oracle**. Remaining headroom ≈ **1.7 Mbps** mean. CA / DLC / LSG cannot close a 16 Mbps gp gap or a path-base p95 of 142 ms.

ACK p95 tracks path p95 + a few ms of frozen QIR. Queue-sojourn pacing (Bet 5) cannot pull mean p95 under 138.8 while path p95 is 142.3.

Terrestrial (unchanged CCA): gp ~78.6 ≥ 77 **PASS**; p95 **46 ms** (path 40 + QIR excess 6). Documented honestly vs the old path-only 40 ms floor.

## What we did not do

- No Crest Abort / Dual-Ledger Cruise / Local Surplus Guard (Bet 1–2). Data killed them before implementation: the gap is geometric, not a reclaim-state-machine miss.
- No SkyPulse PATHHINT assist as a product claim (Bet 3). Endpoint geometry is the blocker.
- No DTCE, EpochMemory, loss-burst gating, relative-only product PASS, orphan PR #5 merge.
- No suite default change. `path_profile="ope_v36"` remains the lock.

## Opt-in realism probes (not the suite default)

`LeoPathConfig.path_profile`:

| Profile | What changes | Oracle gp mean | Path p95 mean | Absolute 75/138.8 geometrically possible? |
|---------|--------------|---------------:|--------------:|-------------------------------------------|
| `ope_v36` (default) | frozen v3.6/v3.7 generative path | 60.48 | 142.32 | **No** |
| `starlink_rtt` | cruise RTT 40–75 ms; HO spike only during the 0.4s loss window; **same 20–120 Mbps cap band** | 60.07 | 70.79 | **No** (p95 yes, gp no) |
| `starlink_v1` | `starlink_rtt` + cap band 40–150 Mbps | 84.03 | 70.79 | **Yes (geometry only)** |

CSV demos: `traces/ope_v36_seed13.csv`, `traces/starlink_rtt_seed13.csv`, `traces/starlink_v1_seed13.csv`.

`starlink_rtt` proves the p95 bar is blocked by **epoch-sticky high RTT** (12s at 150–180 ms), which is not how Starlink handovers behave (brief disruption, then a new satellite still typically 30–70 ms). Fixing RTT stickiness alone does **not** unlock gp≥75.

`starlink_v1` makes the absolute bars geometrically possible by also raising the capacity band. It also raises BBR’s ceiling. **Do not treat 75/138.8 as automatically still the right product bar** on a new model — Jon must decide.

Spec: `docs/leoaware_v38_capacity_model.md`.

## Integrity

| Check | Result |
|-------|--------|
| `python -m experiments.test_ascent_d_integrity` | **PASS** (ASCENT-D + OPE) |
| OPE path identity CUBIC=BBR=LeoAware | **PASS** |
| soft-QIR α frozen 0.20 / 25 ms | **PASS** |
| ope_v36 seed-13 first HO golden | **PASS** (t=10.080s) |
| default geometry still forbids 75/138.8 | **PASS** (guard test) |
| terrestrial excess-RTT | path 40 ms, ACK p95 46 ms, excess 6 ms |

## Gate scorecard (product absolute dual-gate)

| Check | Bar | Result |
|-------|-----|--------|
| gp mean | ≥ 75.0 | **FAIL — oracle 60.48; LeoAware 58.78 (97% of ceiling)** |
| p95 mean | ≤ 138.8 | **FAIL — path-base 142.32; ACK 152.09** |
| terrestrial gp | ≥ 77 | **PASS ~78.6** (p95 46 ms with frozen soft-QIR) |
| integrity | green | **PASS** |
| relative vs BBR | research-only | LeoAware 58.78/152.09 vs BBR 58.21/152.89 (not a product PASS) |

**Decision: REJECT / WIP.** Honest Pareto: LeoAware is already on the OPE ceiling. Next work is path/HO/capacity realism under OPE, then a Jon gate decision, then CCA on the new lock if the bars remain 75/138.8.

## Ask for Jon

1. Keep product bars at absolute 75/138.8 and **change the default generative path** (candidate: opt-in `starlink_v1`, or real Starlink CSVs), then re-lock CCA on that era?  
2. Or keep `ope_v36` as the fair research path and **re-derive** product bars from usable-speed + BBR on that path (not 75/138.8)?  
3. Or ingest real Starlink RTT/capacity CSVs as the product lock and retire the uniform 20–120 / epoch-sticky RTT model?

Until that decision, do not ship more +0.5 vs BBR “wins” as Optimizer breakthroughs.
