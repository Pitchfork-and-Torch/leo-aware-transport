# LeoAware v3.19 — Starlink leftover observability

**Date:** 2026-09-06  
**Branch:** `cursor/starlink-leftover-obs-1989`  
**Era:** synthetic `starlink_v1`  
**Lever:** none (observe only)  
**Decision:** **research hooks only.** Current stays v3.17 FillGap
82.45 / 76.26. SoftCeil stays REJECT. Not paid.

## Why this exists

v3.18 SoftCeil filled the 0.85–0.90 delivery-BDP band and **lost**
(82.35 vs FillGap 82.45 / BBR 82.44). Seed 13 fell 96.80 → 96.31.
The leftover after FillGap is **not** that cruise band. Do not retry a
ceiling raise.

The next cook needs a measured split, not another one-off diag.
These hooks put leftover counters on the official scorecard:

- cruise vs post-detect vs REPROBE ACK share
- leftover-band and still-below-0.85 share in each region
- LSG clamps by region
- detect count vs real path HOs
- path-HO observe is fail-closed (never REPROBE / detect / fill)

## What did not change

- `LeoAwareCCA()` defaults stay FillGap / OpenSlot / SoftCeil **False**
- Dual-gate bars stay gp ≥ 75 and p95 ≤ 138.8
- Soft-QIR α stays 0.20
- No new send-control lever
- No Current / paid bump

## Reproduce

```bash
python3 -m experiments.test_starlink_observability
python3 -m experiments.test_ope_integrity
python3 -m experiments.diag_v319_leftover
```

Official Current reproduce is still `python3 -m experiments.run_starlink --no-soft-ceil`.
That runner now also writes a `leftover_observability` section on the
scorecard. The section is research-only.

Design archive: `results/archive/20260906-v319-leftover/`
