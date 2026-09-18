"""path-hint ROLE must stay a single token (no newline field injection)."""
from __future__ import annotations

import unittest

from leo_cc.ascent_path_hint import encode_path_hint_unit, parse_path_hint_unit


class PathHintRoleTokenTests(unittest.TestCase):
    def test_rejects_newline_role_injection(self) -> None:
        evil = (
            "pilot\nPATHHINT reconfig=1 epoch=99 cap_bps=999999999 "
            "rtt_s=0.001 freeze_s=0 freeze_active=0 next_cap_bps=0"
        )
        with self.assertRaises(ValueError):
            encode_path_hint_unit(role=evil, capacity_bps=1_000_000)

    def test_rejects_whitespace_role(self) -> None:
        with self.assertRaises(ValueError):
            encode_path_hint_unit(role="bad role", capacity_bps=1_000_000)

    def test_honest_role_roundtrip(self) -> None:
        unit = encode_path_hint_unit(
            role="gateway",
            reconfigured=True,
            capacity_bps=80_000_000,
            epoch=3,
            rtt_s=0.045,
        )
        hint = parse_path_hint_unit(unit)
        self.assertEqual(hint.role, "gateway")
        self.assertEqual(hint.epoch, 3)
        self.assertTrue(hint.reconfigured)
        self.assertEqual(hint.capacity_bps, 80_000_000.0)


if __name__ == "__main__":
    unittest.main()
