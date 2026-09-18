"""LeoAwareCCA.on_path_hint: non-finite freeze_remaining_s must not forever-freeze."""
from __future__ import annotations

import math
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from leo_cc.ccas import LeoAwareCCA  # noqa: E402


def test_inf_freeze_remaining_does_not_set_infinite_until() -> None:
    cca = LeoAwareCCA()
    cca.use_path_hints = True
    before = cca.freeze_until
    cca.on_path_hint(1.0, False, freeze_remaining_s=float("inf"), freeze_active=True)
    assert math.isfinite(cca.freeze_until) or cca.freeze_until == before
    # With rem cleared, freeze_active alone may still arm a zero-length freeze at t.
    assert cca.freeze_until != float("inf")


def test_nan_freeze_remaining_does_not_set_nan_until() -> None:
    cca = LeoAwareCCA()
    cca.use_path_hints = True
    cca.on_path_hint(2.0, False, freeze_remaining_s=float("nan"), freeze_active=False)
    assert cca.freeze_until != float("nan") and (
        cca.freeze_until < 0 or math.isfinite(cca.freeze_until)
    )


def test_finite_freeze_still_applies() -> None:
    cca = LeoAwareCCA()
    cca.use_path_hints = True
    cca.on_path_hint(10.0, False, freeze_remaining_s=1.5, freeze_active=True)
    assert cca.freeze_until == 11.5
    assert cca.mode in ("ascent_freeze", "skypulse_freeze")
