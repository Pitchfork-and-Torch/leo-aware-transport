#!/usr/bin/env python3
"""encode_path_hint_unit must require a non-negative int epoch (or None)."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from leo_cc.ascent_path_hint import encode_path_hint_unit, parse_path_hint_unit


def test_rejects_bad_epochs() -> None:
    cases = [
        {"epoch": -1},
        {"epoch": -100},
        {"epoch": 3.7},
        {"epoch": True},
        {"epoch": "5"},
    ]
    for kw in cases:
        try:
            encode_path_hint_unit(**kw)
            raise AssertionError(f"expected ValueError for {kw}")
        except ValueError as exc:
            assert "epoch" in str(exc), exc
    print("PASS test_rejects_bad_epochs")


def test_none_and_nonneg_int_ok() -> None:
    u0 = encode_path_hint_unit(epoch=None, capacity_bps=1e6)
    h0 = parse_path_hint_unit(u0)
    assert h0.epoch is None
    u1 = encode_path_hint_unit(epoch=0, capacity_bps=1e6)
    h1 = parse_path_hint_unit(u1)
    assert h1.epoch == 0
    u2 = encode_path_hint_unit(epoch=3, capacity_bps=1e6)
    h2 = parse_path_hint_unit(u2)
    assert h2.epoch == 3
    print("PASS test_none_and_nonneg_int_ok")


if __name__ == "__main__":
    test_rejects_bad_epochs()
    test_none_and_nonneg_int_ok()
    print("ALL path-hint epoch tests passed")
