#!/usr/bin/env python3
"""Unit checks: ASCENT-D erase-on-fail never applies corrupted path hints."""
from __future__ import annotations

import random
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from leo_cc.ccas import LeoAwareCCA
from leo_cc.ascent_path_hint import (
    encode_path_hint_ascent_d,
    encode_path_hint_unit,
    decode_ascent_d_path_hint,
    decode_plain_path_hint,
    ingest_path_hint_stream,
    bit_flip_noise,
    IngestStats,
)


def test_roundtrip_ok():
    frame = encode_path_hint_ascent_d(
        reconfigured=True,
        capacity_bps=80e6,
        rtt_s=0.05,
        epoch=3,
        freeze_remaining_s=0.1,
        freeze_active=True,
        next_capacity_bps=70e6,
        role="pilot",
    )
    hint, nxt, status = decode_ascent_d_path_hint(frame)
    assert status == "ok", status
    assert hint is not None
    assert hint.reconfigured is True
    assert hint.capacity_bps == 80e6
    assert hint.epoch == 3
    assert hint.role == "pilot"
    assert nxt == len(frame)
    print("ok: roundtrip")


def test_erase_on_corruption():
    frame = encode_path_hint_ascent_d(
        reconfigured=True,
        capacity_bps=90e6,
        epoch=7,
        role="pilot",
    )
    rng = random.Random(99)
    # Flip many bits past RS correction capability
    bad = bit_flip_noise(frame, 80, rng)
    hint, nxt, status = decode_ascent_d_path_hint(bad)
    assert status in ("erased", "truncated", "no_sync"), status
    assert hint is None
    print(f"ok: erase status={status}")


def test_fail_closed_no_rate_change():
    cca = LeoAwareCCA(use_path_hints=True)
    cca.cwnd = 100_000
    before = cca.cwnd
    before_rec = cca.reconfigs_detected

    good = encode_path_hint_ascent_d(
        reconfigured=True, capacity_bps=100e6, epoch=1, role="pilot"
    )
    stats = IngestStats()
    ingest_path_hint_stream(cca, good, now=1.0, stats=stats)
    assert stats.applied == 1
    assert cca.reconfigs_detected == before_rec + 1
    after_good_cwnd = cca.cwnd

    # Corrupted frame must not change state further
    bad = bit_flip_noise(good, 100, random.Random(3))
    cwnd_mid = cca.cwnd
    rec_mid = cca.reconfigs_detected
    stats2 = IngestStats()
    ingest_path_hint_stream(cca, bad, now=2.0, stats=stats2)
    assert stats2.applied == 0
    assert stats2.erased >= 1 or stats2.no_sync >= 1 or stats2.truncated >= 1
    assert cca.cwnd == cwnd_mid
    assert cca.reconfigs_detected == rec_mid
    assert before != after_good_cwnd or cca.reconfigs_detected > before_rec
    print("ok: fail-closed (erased => zero apply)")


def test_plain_unit():
    unit = encode_path_hint_unit(reconfigured=True, capacity_bps=50e6, epoch=2)
    assert all(b < 0x80 for b in unit)
    hint = decode_plain_path_hint(unit)
    assert hint.reconfigured and hint.capacity_bps == 50e6
    print("ok: plain sacred-ASCII unit")


def test_role_reject():
    cca = LeoAwareCCA(use_path_hints=True)
    rec0 = cca.reconfigs_detected
    frame = encode_path_hint_ascent_d(
        reconfigured=True, capacity_bps=60e6, epoch=9, role="untrusted:external"
    )
    stats = IngestStats()
    ingest_path_hint_stream(cca, frame, now=1.0, stats=stats)
    assert stats.role_rejected == 1
    assert stats.applied == 0
    assert cca.reconfigs_detected == rec0
    print("ok: role reject")


def test_skypulse_freeze_only_no_hint_reprobe():
    """Growth-freeze ingest must not cut via hint REPROBE."""
    cca = LeoAwareCCA(use_path_hints=True, hint_freeze_only=True)
    rec0 = cca.reconfigs_detected
    frame = encode_path_hint_ascent_d(
        reconfigured=True, capacity_bps=80e6, epoch=4, role="pilot"
    )
    stats = IngestStats()
    ingest_path_hint_stream(cca, frame, now=1.0, stats=stats)
    assert stats.applied == 1
    assert cca.reconfigs_detected == rec0
    assert cca.ascent_d_applied == 1
    print("ok: SkyPulse freeze-only skips hint REPROBE")


def test_skypulse_does_not_gate_loss_burst():
    """Freeze window must not suppress ep:loss_burst."""
    cca = LeoAwareCCA(use_path_hints=True, hint_freeze_only=True)
    cca.min_rtt = 0.05
    cca.rtt_hist.extend([0.05, 0.051, 0.049, 0.05])
    cca.last_reconfig_t = -10.0
    cca.freeze_until = 10.0
    rec0 = cca.reconfigs_detected
    t = 5.0
    cca.on_loss(t, 1200, congestive=False)
    cca.on_loss(t + 0.05, 1200, congestive=False)
    assert cca.reconfigs_detected == rec0 + 1, (cca.reconfigs_detected, cca.mode)
    assert cca.mode == "ser:loss_burst" or str(cca.mode).startswith("ser"), cca.mode
    print("ok: SkyPulse freeze does not gate ep:loss_burst")


def test_far_hold_default_off_does_not_change_ascent():
    cca = LeoAwareCCA(use_path_hints=True)
    assert cca.use_far_hold is False
    print("ok: FarHold default off on ASCENT path")


if __name__ == "__main__":
    test_roundtrip_ok()
    test_erase_on_corruption()
    test_fail_closed_no_rate_change()
    test_plain_unit()
    test_role_reject()
    test_skypulse_freeze_only_no_hint_reprobe()
    test_skypulse_does_not_gate_loss_burst()
    test_far_hold_default_off_does_not_change_ascent()
    from experiments.test_ope_integrity import run_all as run_ope
    run_ope()
    print("ALL ASCENT-D integrity tests passed")
