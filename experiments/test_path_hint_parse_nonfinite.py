"""path-hint parse must ignore NaN/Inf wire metrics (not apply them)."""

from __future__ import annotations

import math
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from leo_cc.ascent_path_hint import parse_path_hint_unit  # noqa: E402


def test_parse_inf_rtt_ignored() -> None:
    unit = (
        b"ASCENT/1.0\nROLE:pilot\n"
        b"PATHHINT reconfig=0 epoch=1 cap_bps=80000000 rtt_s=inf "
        b"freeze_s=0 freeze_active=0 next_cap_bps=0"
    )
    hint = parse_path_hint_unit(unit)
    assert hint.rtt_s is None
    assert hint.capacity_bps == 80_000_000.0


def test_parse_inf_freeze_not_active() -> None:
    unit = (
        b"ASCENT/1.0\nROLE:pilot\n"
        b"PATHHINT reconfig=0 epoch=1 cap_bps=1 rtt_s=0.04 "
        b"freeze_s=inf freeze_active=0 next_cap_bps=0"
    )
    hint = parse_path_hint_unit(unit)
    assert hint.freeze_remaining_s is None
    assert hint.freeze_active is False


def test_parse_nan_capacity_ignored() -> None:
    unit = (
        b"ASCENT/1.0\nROLE:pilot\n"
        b"PATHHINT reconfig=0 epoch=1 cap_bps=nan rtt_s=0.04 "
        b"freeze_s=0 freeze_active=0 next_cap_bps=nan"
    )
    hint = parse_path_hint_unit(unit)
    assert hint.capacity_bps is None
    assert hint.next_capacity_bps is None
    assert hint.rtt_s == 0.04


def test_parse_finite_ok() -> None:
    unit = (
        b"ASCENT/1.0\nROLE:pilot\n"
        b"PATHHINT reconfig=1 epoch=3 cap_bps=70000000 rtt_s=0.045 "
        b"freeze_s=0.12 freeze_active=0 next_cap_bps=60000000"
    )
    hint = parse_path_hint_unit(unit)
    assert hint.capacity_bps == 70_000_000.0
    assert hint.rtt_s == 0.045
    assert hint.freeze_remaining_s == 0.12
    assert hint.freeze_active is True  # freeze_s > 0 forces active
    assert math.isfinite(hint.rtt_s)


if __name__ == "__main__":
    test_parse_inf_rtt_ignored()
    test_parse_inf_freeze_not_active()
    test_parse_nan_capacity_ignored()
    test_parse_finite_ok()
    print("PASS test_path_hint_parse_nonfinite")
