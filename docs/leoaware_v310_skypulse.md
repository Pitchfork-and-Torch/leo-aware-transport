# LeoAware v3.10 SkyPulse PATHHINT — REJECT (hybrid)

**Date:** 2026-08-13  
**Branch:** `cursor/v310-halo-84b8`  
**Decision:** **REJECT** hybrid. Product CCA remains **v3.9 Crest** endpoint-only.  
**Not Current. No paid bump. Do not merge.**

## Bet

SkyPulse PATHHINT ingest, **growth-freeze only**, via the **existing**
ASCENT-D path (`leo_cc/ascent_path_hint.py`, `path_hint_mode=ascent_d`).
No second ingest path.

| Rail | How |
|------|-----|
| Growth-freeze only | `hint_freeze_only=True`: hold cwnd growth in the freeze window |
| Never hint-REPROBE | Reconfig / freeze-end do **not** call `_enter_reprobe` |
| Never gate `ep:loss_burst` | Detect stays live during SkyPulse freeze (integrity test) |
| Fail-closed | Erased ASCENT-D frames: zero apply (existing) |
| Public suite | Still endpoint-only (`use_path_hints=False`) |

## Ingest

PATHHINT **can** be ingested in this harness. Hybrid `leo_fast_ho` applied
14–16 ASCENT-D frames per seed (HO + freeze edges). Soft-QIR α frozen 0.20.

## Two tables (do not mix)

Fair lock: `starlink_v1`, 90s, seeds 13,7,42,99,123.

### Endpoint-only (Crest defaults, `path_hint_mode=none`)

| CCA | gp mean | p95 mean | terr gp |
|-----|--------:|---------:|--------:|
| **LeoAware endpoint** | **82.089** | **76.264** | **78.623** |
| Crest published | 82.09 | 76.26 | 78.62 |

Per-seed gp/p95: 13→96.65/72.21 · 7→75.01/67.81 · 42→80.67/97.56 · 99→72.83/64.09 · 123→85.28/79.65

**No endpoint regression** vs Crest 82.09/76.26 (same means).

### Hybrid (ASCENT-D + `hint_freeze_only`)

| CCA | gp mean | p95 mean | terr gp |
|-----|--------:|---------:|--------:|
| **LeoAware hybrid** | **81.936** | **75.464** | **78.623** |
| BBRv3approx | 82.439 | 76.664 | — |

Per-seed hybrid gp/p95: 13→96.28/72.21 · 7→74.94/67.81 · 42→80.58/**93.56** · 99→72.69/64.09 · 123→85.19/79.65

Seed 42 p95 97.56→93.56 is the only p95 move. Every seed lost a little gp.

## Gates

| Check | Result |
|-------|--------|
| Endpoint no regression vs Crest | **PASS** (82.089/76.264) |
| Hybrid gp ≥ 75 | **81.936 PASS** |
| Hybrid p95 ≤ 138.8 | **75.464 PASS** |
| Hybrid terr ≥ 77 | **78.623 PASS** |
| Integrity | **PASS** |
| Hybrid Pareto vs Crest (gp↑ w/o p95↑ **or** p95↓ w/o gp↓) | **FAIL** (p95↓ and gp↓) |

**Decision: REJECT.** `use_path_hints=False`, `hint_freeze_only=False` on the
product path. Crest stays default.

Reproduce:

```bash
python -m experiments.test_ascent_d_integrity
python -m experiments.run_skypulse --tag 20260813-v310-skypulse
```

Archive: `results/archive/20260813-v310-skypulse/`
