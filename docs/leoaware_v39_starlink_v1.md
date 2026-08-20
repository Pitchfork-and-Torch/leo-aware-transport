# LeoAware v3.9 Crest: starlink_v1 product-lock era

**Date:** 2026-08-12  
**Branch:** `cursor/v39-starlink-v1-ae43`  
**Decision:** **ACCEPT** absolute dual-gate on `starlink_v1` (means: gp 82.07 / p95 76.26 / terr 78.62). **Prior lock — no longer Current.** Current is v3.17 FillGap 82.45 / 76.26 (`docs/leoaware_v317_fillgap.md`).  
**Scope:** Synthetic `starlink_v1` harness era (still the product path).

## Decision that created this era

PR #8 / Step 0 proved absolute **gp≥75 AND p95≤138.8** is geometrically
impossible on `ope_v36` (oracle ~60.5, path p95 ~142). Jon/Steward: **keep the
absolute bars**, change the **default product-lock path** to documented
`starlink_v1`, then re-lock CCA. Real Starlink CSVs are the north star next
(`docs/starlink_csv_ingest.md`).

`ope_v36` remains the research relative-BBR path. **Do not mix eras** in Current
hero tables. See `docs/harness_eras.md`.

## Path

`starlink_v1` (from Step 0, now the product default):

- Cruise RTT: 30 ms + U(10,45) ms → ~40–75 ms; 12% extra +10–25 ms
- HO spike: U(20,55) ms **only** during `reconfig_loss_window_s` (0.4 s)
- Capacity: U(40, 150) Mbps
- OPE kept (`loss_rng` orthogonal to `path.rng`)
- Soft-QIR α **frozen 0.20** / 25 ms

Step 0 geometry (90s, seeds 13,7,42,99,123): oracle gp **84.03**, path p95
**70.79** — absolute bars are geometrically possible.

## Lock result (means, not peaks)

Fair CUBIC + BBRv3approx + LeoAware, same `starlink_v1` path, seeds
13,7,42,99,123, 90s endpoint, soft-QIR α=0.20.

| CCA | gp mean | p95 mean |
|-----|--------:|---------:|
| CUBIC | 8.57 | 71.63 |
| BBRv3approx | 82.44 | 76.66 |
| **LeoAware v3.9 Crest** | **82.07** | **76.26** |

Terrestrial LeoAware **78.62** @ 46 ms p95 (path 40 + QIR). Integrity green.
OPE identity PASS. Seed 99 LeoAware gp 72.83 is below 75 (oracle 74.63); the
bar is the mean.

Product PASS is **absolute 75/138.8**, not relative-to-BBR. LeoAware and BBR
are tied on this orbit. Do not mix with `ope_v36` ~58/152. No paid landing
bump — synthetic path until `docs/starlink_csv_ingest.md`.

Archive: `results/archive/20260812-v39-starlink-v1/`

## Invention ablation (not a Current bump)

`python -m experiments.crest_ablation` · seeds 13,7,42,99,123 · `leo_fast_ho` · `starlink_v1`

| Variant | gp mean | p95 mean | dual-gate |
|---------|--------:|---------:|-----------|
| BBRv3approx | 82.44 | 76.66 | yes |
| v37_oce (flags off) | 82.28 | 76.66 | yes |
| CA-only | 82.28 | 76.66 | yes |
| CA+DLC+LSG | 81.98 | 76.26 | yes |
| v39_full | 82.07 | 76.26 | yes |

Plain v3.7-style LeoAware already clears 75/138.8 on this path. Crest flags are **not** load-bearing; the generative era switch is. CA is a no-op here. DLC+LSG is a ~0.4 ms p95 trim (seed 123) at ~0.3 Mbps gp. Keep v39_full as the documented lock stack; do not retune for 0.2 Mbps. Measured CSV eras (`wetlinks_v1`, `zhao_zenodo23`) are research-only and must not be mixed with these numbers.

Archive: `results/archive/20260812-v39-crest-ablation/`

## Invention stack (endpoint-only product gate)

Tried in order. No DTCE, no ghost/shadow REPROBE, no EpochMemory, **never gate
`ep:loss_burst`**.

### 1. Crest Abort (CA-hard)

Abort TBPR / OCE reclaim on RTT crest: `rtt > k × recent_median` with k≈1.35
(range [1.30, 1.45]). Hysteresis: 2 consecutive crest samples **or** crest +
rising `delay_ratio`. **Cruise/reclaim only** — does not fire during REPROBE
explore/fill. Drops cwnd to the safe ledger / commit point.

### 2. Dual-Ledger Cruise (DLC)

Two ledgers: `cwnd_safe` (~1.05–1.08× BDP) vs `cwnd_tide` (stretch ≤1.42× BDP).
Fly tide only if delay is clean **and** no crest. Shares the CA signal. This is
**not** DTCE (no cross-epoch lo/hi fill race).

### 3. Local Surplus Guard (LSG)

Cruise stretch only if delivery-rate EWMA ≥ ~0.85× `prior_bw` and local RTT is
healthy. Does not veto an armed OCE/TBPR window (those have CA + delay abort).
No multi-seed online budget. No seed-id branching.

### 4. Optional freeze-only anticipator

On endpoint ACK-IA (without a detect hit): hold growth ~120 ms. **Never
suppresses detection.** If `ep:loss_burst` / RTT-MAD then fires, REPROBE owns
the hop.

## Reproduce

```bash
python -m experiments.test_ascent_d_integrity
python -m experiments.ope_feasibility --profiles ope_v36,starlink_v1
python -m experiments.multi_seed --tag 20260812-v39-starlink-v1
python -m experiments.crest_ablation --tag 20260812-v39-crest-ablation
python -m experiments.multi_seed --path-profile ope_v36 --tag 20260812-v39-ope-research
```

Archive: `results/archive/20260812-v39-starlink-v1/`  
Capacity: `docs/leoaware_v38_capacity_model.md` (updated for the era switch)  
CSV next: `docs/starlink_csv_ingest.md`
