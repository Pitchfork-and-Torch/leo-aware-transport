"""parse_path_hint_unit: negative wire epoch (≠ -1 sentinel) must be ignored."""
from __future__ import annotations

from leo_cc.ascent_path_hint import parse_path_hint_unit, encode_path_hint_unit


def test_negative_epoch_ignored() -> None:
    for bad in (-2, -5, -100):
        unit = (
            f"ASCENT/1.0\nROLE:pilot\nPATHHINT reconfig=0 epoch={bad} "
            "cap_bps=1000 rtt_s=0.04 freeze_s=0.0 freeze_active=0 next_cap_bps=0"
        ).encode("ascii")
        h = parse_path_hint_unit(unit)
        assert h.epoch is None, f"epoch={bad} parsed as {h.epoch}"


def test_sentinel_and_good_epoch() -> None:
    h = parse_path_hint_unit(
        b"ASCENT/1.0\nROLE:pilot\nPATHHINT epoch=-1 cap_bps=1000"
    )
    assert h.epoch is None
    h2 = parse_path_hint_unit(
        b"ASCENT/1.0\nROLE:pilot\nPATHHINT epoch=3 cap_bps=1000"
    )
    assert h2.epoch == 3
    wire = encode_path_hint_unit(epoch=7, capacity_bps=1e6, role="pilot")
    assert parse_path_hint_unit(wire).epoch == 7


if __name__ == "__main__":
    test_negative_epoch_ignored()
    test_sentinel_and_good_epoch()
    print("PASS test_path_hint_parse_negative_epoch")
