#!/usr/bin/env python3
"""encode_path_hint_unit must reject negative capacity/RTT/freeze fields."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from leo_cc.ascent_path_hint import encode_path_hint_unit, parse_path_hint_unit


def test_rejects_negatives() -> None:
    cases = [
        {"capacity_bps": -1.0},
        {"next_capacity_bps": -2.0},
        {"rtt_s": -0.01},
        {"freeze_remaining_s": -3.0},
    ]
    for kw in cases:
        try:
            encode_path_hint_unit(**kw)
            raise AssertionError(f"expected ValueError for {kw}")
        except ValueError as exc:
            assert "must be >= 0" in str(exc), exc
    print("PASS test_rejects_negatives")


def test_zero_and_positive_still_encode() -> None:
    u = encode_path_hint_unit(
        capacity_bps=0.0,
        next_capacity_bps=50e6,
        rtt_s=0.0,
        freeze_remaining_s=0.0,
        epoch=3,
    )
    h = parse_path_hint_unit(u)
    assert h.epoch == 3
    assert h.next_capacity_bps == 50e6
    # 0 remains the wire sentinel for "absent" capacity/rtt
    assert h.capacity_bps is None
    assert h.rtt_s is None
    print("PASS test_zero_and_positive_still_encode")


if __name__ == "__main__":
    test_rejects_negatives()
    test_zero_and_positive_still_encode()
    print("ALL path-hint nonnegative tests passed")
