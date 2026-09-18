"""path-hint encode must reject NaN/Inf metrics (not serialize them)."""

from __future__ import annotations

import math
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from leo_cc.ascent_path_hint import encode_path_hint_unit  # noqa: E402


def _rejects(**kwargs) -> None:
    try:
        encode_path_hint_unit(**kwargs)
    except ValueError as exc:
        assert "finite" in str(exc) or ">=" in str(exc), exc
        return
    raise AssertionError(f"expected ValueError for {kwargs}")


def test_reject_nan_rtt() -> None:
    _rejects(rtt_s=float("nan"))


def test_reject_inf_rtt() -> None:
    _rejects(rtt_s=float("inf"))


def test_reject_inf_freeze() -> None:
    _rejects(freeze_remaining_s=float("inf"))


def test_reject_nan_capacity() -> None:
    _rejects(capacity_bps=float("nan"))


def test_finite_ok() -> None:
    unit = encode_path_hint_unit(rtt_s=0.045, capacity_bps=80_000_000)
    assert b"rtt_s=0.045000" in unit
    assert math.isfinite(0.045)


if __name__ == "__main__":
    test_reject_nan_rtt()
    test_reject_inf_rtt()
    test_reject_inf_freeze()
    test_reject_nan_capacity()
    test_finite_ok()
    print("PASS test_path_hint_nonfinite")
