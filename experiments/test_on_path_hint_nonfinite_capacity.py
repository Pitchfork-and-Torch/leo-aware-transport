"""LeoAwareCCA.on_path_hint: non-finite capacity must not poison hint_capacity_bps."""
from __future__ import annotations

import math
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from leo_cc.ccas import LeoAwareCCA  # noqa: E402


def test_inf_capacity_bps_ignored() -> None:
    cca = LeoAwareCCA()
    cca.use_path_hints = True
    before = cca.hint_capacity_bps
    cca.on_path_hint(1.0, False, capacity_bps=float("inf"))
    assert cca.hint_capacity_bps == before
    assert math.isfinite(cca.hint_capacity_bps) or cca.hint_capacity_bps == 0.0


def test_nan_next_capacity_bps_ignored() -> None:
    cca = LeoAwareCCA()
    cca.use_path_hints = True
    before = cca.hint_capacity_bps
    cca.on_path_hint(1.0, False, next_capacity_bps=float("nan"))
    assert cca.hint_capacity_bps == before
    assert cca.hint_capacity_bps == cca.hint_capacity_bps  # not NaN


def test_bool_capacity_bps_ignored() -> None:
    cca = LeoAwareCCA()
    cca.use_path_hints = True
    before = cca.hint_capacity_bps
    cca.on_path_hint(1.0, False, capacity_bps=True)  # type: ignore[arg-type]
    assert cca.hint_capacity_bps == before


def test_finite_capacity_still_applies() -> None:
    cca = LeoAwareCCA()
    cca.use_path_hints = True
    cca.on_path_hint(1.0, False, capacity_bps=80_000_000.0)
    assert cca.hint_capacity_bps == 80_000_000.0
