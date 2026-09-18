# Changelog

Package version tracks the public tree. Current product CCA lock is
separate and does not move on REJECT or observe-only cooks.

Dual-gate bars stay gp >= 75 and p95 <= 138.8 on `starlink_v1`.
Current means stay 82.45 / 76.26 (v3.17 FillGap). This file does not
retune congestion-control math.

## 0.3.22 - 2026-09-17

- Congestive enqueue drops in `leo_cc.sim` now `on_sent` before `on_loss`.
  `on_loss` always calls `on_delivered`, so a drop of a never-sent MSS used to
  free prior inflight and let cwnd admit an extra segment. Integrity test:
  `experiments/test_congestive_enqueue_inflight.py`. No CCA / dual-gate change.

- `path_hint_mode="direct"` now edge-gates on reconfig / freeze-enter like
  `ascent_d` / `ascent_plain`. Per-slot direct emits re-applied LeoAware's
  freeze `cwnd * 0.97` cut every 10 ms (~15x per freeze window) and made
  direct harsher than the ASCENT-D path it stands in for. Endpoint-only
  (`use_path_hints=False`) product path unchanged. Integrity test:
  `experiments/test_direct_hint_edge_gate.py`.

- Declare `reedsolo>=1.7` in `pyproject.toml`. `leo_cc.ascent_d` imports
  it at module load and `leo_cc.sim` pulls it in transitively, so
  `pip install .` produced a package whose `leo-run` entry point and
  `import leo_cc.sim` failed with `ModuleNotFoundError`. `requirements.txt`
  already had it; the two lists now match.
- `experiments/test_ascent_d_integrity.py` checks that every package in
  `requirements.txt` is declared in `pyproject.toml` and that the package
  version matches `leo_cc.__version__`.
- README `**Package:**` line now matches 0.3.22 (was left at 0.3.21); the
  integrity test asserts that README line stays lockstep with
  `leo_cc.__version__`.
- No congestion-control change. Current stays v3.17 FillGap 82.45 / 76.26.

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
