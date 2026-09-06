# LeoAware v3.20 — detect over-fire measure

**Date:** 2026-09-06  
**Branch:** `cursor/detect-overfire-2daf`  
**Era:** synthetic `starlink_v1`  
**Lever:** none (observe + shadow gates)  
**Decision:** **research measure.** Current stays v3.17 FillGap
82.45 / 76.26. SoftCeil stays REJECT. Not paid.

## Why this exists

v3.19 leftover hooks confirmed **H2 detect over-fire** (~56 detects vs
7–8 path HOs, ~8×). SoftCeil already showed the leftover is not the
0.85–0.90 cruise band. This cook **measures** those extra detects
before anyone fills a tighter gate.

v2.1 already rejected a blunt fusion-threshold raise (1.55 → 1.85)
on an older harness (gp 64.82 → 62.32). Do not retry that blindly.
`ep:loss_burst` stays ungated. Path HO is observe-only and is never
a live detect input.

## What changed

- Always-on endpoint-detect event log on `LeoAwareCCA` (t / reason / score)
- `classify_detect_overfire` + `detect_overfire_hook` (dual-gate bars
  stay gp ≥ 75 / p95 ≤ 138.8)
- Shadow gates, all endpoint-legal: `score_ge_1_85`, `score_ge_2_0`,
  `multi_reason`, `rtt_anchor`
- `python3 -m experiments.diag_v320_detect` on the FillGap lock path

No send-control lever. Constructor defaults stay False. Detect
threshold 1.65 and cooldown 0.42 stay untouched.

## Official bars

Same product dual-gate as every `starlink_v1` scorecard:

| Check | Bar |
|-------|-----|
| gp mean | ≥ 75.0 |
| p95 mean | ≤ 138.8 |
| Current bump | must clearly beat FillGap 82.45 / 76.26 |

## Reproduce

```bash
python3 -m experiments.test_starlink_observability
python3 -m experiments.test_ope_integrity
python3 -m experiments.test_ascent_d_integrity
python3 -m experiments.diag_v320_detect
```

Current reproduce is still `python3 -m experiments.run_starlink --no-soft-ceil`.

Archive: `results/archive/20260906-v320-detect/`
