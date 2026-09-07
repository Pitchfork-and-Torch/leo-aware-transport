# Changelog

Package version tracks the public tree. Current product CCA lock is
separate and does not move on REJECT or observe-only cooks.

Dual-gate bars stay gp >= 75 and p95 <= 138.8 on `starlink_v1`.
Current means stay 82.45 / 76.26 (v3.17 FillGap). This file does not
retune congestion-control math.

## 0.3.21 - 2026-09-07

- Align package version in `pyproject.toml` and `leo_cc.__version__`
  (was 0.1.0 / 0.3.9 Crest comment).
- Current product lock remains v3.17 FillGap on `starlink_v1`
  (82.45 / 76.26, seeds 13, 7, 42, 99, 123).
- Tree includes later research cooks that did not bump Current:
  v3.18 SoftCeil REJECT (82.35 / 76.26), v3.19 leftover observe,
  v3.20 detect over-fire observe, v3.21 on_loss taxonomy
  (REJECT a live loss-burst gate).

## 0.3.17 - 2026-08-20

- FillGap promoted to Current product dual-gate lock on `starlink_v1`
  (82.45 / 76.26). Constructor defaults stay `use_fill_gap=False` /
  `use_openslot=False`. Prior lock: v3.9 Crest 82.07 / 76.26.

## 0.3.9 - 2026-08-12

- Crest prior product lock on `starlink_v1` (82.07 / 76.26).
