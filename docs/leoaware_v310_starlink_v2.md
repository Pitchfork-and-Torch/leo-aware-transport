# starlink_v2 — opt-in mid-epoch capacity flicker (research)

**Date:** 2026-08-13  
**Status:** opt-in research profile. **Not the product lock.** Product remains
`starlink_v1` (Current = v3.17 FillGap; prior lock v3.9 Crest ACCEPT).

## Motivation

`starlink_v1` redraws capacity only at handovers. Real Starlink downlink also
flickers inside an epoch. Mid-epoch steps are the natural stress for BBR’s
stale max-filter vs a LEO-aware fade/rise response.

## Profile

Same as `starlink_v1`, plus:

- Every ~2.8s ±1.2s redraw `_cap` in the 40–150 Mbps band
- **No** `reconfigured` flag, **no** loss burst, **no** HO RTT spike
- Flicker schedule consumes `path.rng` (OPE identity across CCAs preserved)

```bash
python -m experiments.multi_seed --path-profile starlink_v2 --tag YYYYMMDD-v2-flicker
```

## Geometry (90s, seeds 13,7,42,99,123, dt=50ms)

| profile | oracle gp mean | path p95 mean | flickers/seed |
|---------|---------------:|--------------:|--------------:|
| starlink_v1 | ~84.0 | 70.79 | 0 |
| starlink_v2 | ~94.3 | 72.79 | ~28 |

Absolute 75/138.8 remains geometrically possible. Higher oracle is expected
(more time near upper-band draws).

## First CCA probe (Crest defaults, no Halo/CFR)

| CCA | gp mean | p95 mean |
|-----|--------:|---------:|
| BBRv3approx | 92.56 | 78.09 |
| LeoAware Crest | 91.97 | 78.09 |

Leo still **behind** BBR (~0.6 Mbps). CFR/CRE ablation did not close it
(CFR≈0 fires; CRE lifts ~7/seed without gp win). Do **not** promote v2 to
product lock on this evidence.

## Integrity

- OPE path identity still required (same HO/RTT/cap timeline across CCAs).
- Soft-QIR α frozen 0.20.
- `ope_v36` / `starlink_v1` generative defaults unchanged.

## Next if Jon cares about flicker

1. Re-tune fade/rise thresholds against per-seed delivery traces (instrumented).
2. Or ingest real CSVs and retire the synthetic flicker generator.
3. Only then consider a product-era switch + bar re-derivation.
