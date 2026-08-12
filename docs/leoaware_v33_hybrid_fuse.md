# LeoAware v3.3: Hybrid fuse (A) + false-REPROBE budget (C)

**Date:** 2026-08-11
**Branch:** `pr-a-hybrid-fuse`
**Scope:** Research prototype. Public suite default remains endpoint-only
(`use_path_hints=False`, `use_orb_signals=False`).

## Problem

1. v3.2 hybrid over-cut when Orb pathID REPROBE stacked on ASCENT freeze/REPROBE;
   Orb util-MD fought reclaim.
2. Endpoint false REPROBE rate left multi-seed `leo_fast_ho` LeoAware below
   BBRv3approx (~66.6 vs ~70.9 Mbps mean goodput).

## Ship A - Hybrid fuse (invert ownership)

1. `_should_suppress_orb_reprobe(t)` for orb-only assist/freeze/REPROBE windows.
2. **Hybrid invert:** ASCENT provides freeze + capacity seed (no stacked cut);
   Orb pathID owns the REPROBE cut, queued across ASCENT freeze.
3. Hybrid: never Orb util-MD; never Orb empty-queue mobility marks.
4. Orb-only util-MD: U high AND queue non-trivial, outside freeze/reprobe.
5. Belt-and-suspenders: hybrid allows Orb cut after freeze even if assist seeded.
6. Endpoint soft cut fixed at 0.58 (v3.1); public suite gate not redefined.

## Ship C - False-REPROBE budget

```
budget ~= k * (1 + elapsed / ho_interval_prior)   # k=2.0, prior=16s
```

When detections exceed budget and `delay_ratio` healthy: raise fusion
`score_threshold` and classic absolute jump floor. Relaxes under 0.85x budget.

## Accept results (fast ablation seeds 13+7, 45s)

| Check | Bar | Result |
|-------|-----|--------|
| integrity | green | PASS |
| ascent_d_noisy applied | 0; == endpoint | PASS |
| hybrid leo_single gp | >= 0.95x endpoint | PASS (72.6 >= 65.7) |
| hybrid leo_fast_ho gp | >= orb - 3 | PASS (85.5 >= 79.1) |
| hybrid p95 | <= endpoint | PASS (100.5 <= 123.9) |
| terrestrial | >= 76 @ 40ms | PASS (76.9) |

## Multi-seed endpoint (90s, seeds 13,7,42,99,123)

| Scenario | v3.2 current LeoAware gp / p95 | v3.3 LeoAware gp / p95 | BBR gp |
|----------|-------------------------------:|-----------------------:|-------:|
| leo_fast_ho | 66.56 / 155.0 | **78.06 / 149.7** | 70.88 |
| leo_single | 61.47 / 128.0 | **72.38 / 141.6** | 58.39 |
| terrestrial | 77.35 / 40.0 | **77.43 / 40.0** | 78.81 |

`leo_fast_ho` mean goodput beats BBR (78.06 > 70.88). Terrestrial holds.

Archive: `results/archive/20260811-v33-hybrid-fuse/`

## Risks

- Hybrid invert couples Orb pathID timing to ASCENT freeze-end; if Orb
  telemetry is absent, hybrid degrades to ASCENT seed without Orb cut.
- Budget too tight could miss a noisy true hop (classic jump floor remains).
- Slot-based sim; not real Starlink / quiche.
