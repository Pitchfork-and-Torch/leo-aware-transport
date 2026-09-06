#!/usr/bin/env python3
"""Starlink leftover observability + frozen dual-gate hooks.

Research only. Does not bump Current. SoftCeil / FillGap defaults stay off.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from leo_cc.ccas import LeoAwareCCA
from leo_cc.harness import (
    PRODUCT_GP_BAR,
    PRODUCT_P95_BAR,
    PRODUCT_PATH_PROFILE,
    PRODUCT_TERR_GP_BAR,
)
from leo_cc.network import LeoPathConfig
from leo_cc.observability import (
    BBR_GP_LOCK,
    FILLGAP_GP_LOCK,
    FILLGAP_P95_LOCK,
    NEAR_HO_WINDOW_S,
    SHADOW_GATE_NAMES,
    SNAPSHOT_FRAC_KEYS,
    SOFTCEIL_GP_REJECT,
    classify_detect_overfire,
    detect_overfire_hook,
    dual_gate_bars,
    leftover_scorecard_hook,
)
from leo_cc.sim import run_sim


def test_dual_gate_bars_frozen():
    bars = dual_gate_bars()
    assert PRODUCT_PATH_PROFILE == "starlink_v1"
    assert bars["gp_mean"] == 75.0 == PRODUCT_GP_BAR
    assert bars["p95_mean"] == 138.8 == PRODUCT_P95_BAR
    assert bars["terr_gp"] == 77.0 == PRODUCT_TERR_GP_BAR
    assert bars["fillgap_gp_lock"] == FILLGAP_GP_LOCK == 82.45
    assert bars["fillgap_p95_lock"] == FILLGAP_P95_LOCK == 76.26
    assert bars["bbr_gp_lock"] == BBR_GP_LOCK == 82.44
    assert bars["softceil_gp_reject"] == SOFTCEIL_GP_REJECT == 82.35
    print("ok: dual-gate bars frozen (75 / 138.8); Current citation FillGap")


def test_scorecard_hook_never_marks_current():
    hook = leftover_scorecard_hook(leo_snaps=[], leo_gp=82.45, leo_p95=76.26)
    assert hook["current_paid"] is False
    assert hook["current_stays"] == "v3.17 FillGap"
    assert hook["softceil_decision"] == "REJECT"
    assert hook["bars"]["gp_mean"] == 75.0
    print("ok: leftover scorecard hook never marks Current / paid")


def test_snapshot_is_read_only():
    cca = LeoAwareCCA()
    assert cca.use_fill_gap is False
    assert cca.use_soft_ceil is False
    assert cca.use_openslot is False
    cca.min_rtt = 0.05
    cca.bw_est = 80e6
    cca.cwnd = 40 * 1200
    cca.delivered_marks.append((1.0, 0.0))
    cca.delivered_marks.append((1.2, 80e6 * 0.2 / 8.0))
    before = (cca.cwnd, cca.mode, cca.reconfigs_detected, cca.fillgap_fills)
    snap = cca.observability_snapshot()
    cca._observe_leftover(2.0, 0.05)
    after = (cca.cwnd, cca.mode, cca.reconfigs_detected, cca.fillgap_fills)
    assert after == before, (before, after)
    assert snap["use_fill_gap"] is False
    assert snap["use_soft_ceil"] is False
    assert cca.obs_acks == 1
    print("ok: leftover observe is read-only (no cwnd / detect / fill)")


def test_path_ho_observe_does_not_reprobe():
    cca = LeoAwareCCA()
    rec0 = cca.reconfigs_detected
    mode0 = cca.mode
    cwnd0 = cca.cwnd
    cca.on_path_epoch_observe(3.0, True)
    assert cca.obs_path_handovers == 1
    assert cca._obs_last_path_ho_t == 3.0
    assert cca.reconfigs_detected == rec0
    assert cca.mode == mode0
    assert cca.cwnd == cwnd0
    cca.on_path_epoch_observe(4.0, False)
    assert cca.obs_path_handovers == 1
    print("ok: path HO observe never REPROBE / detect")


def test_short_starlink_v1_leftover_split():
    cfg = LeoPathConfig(
        duration_s=8.0,
        handover_interval_s=4.0,
        handover_jitter_s=1.0,
        seed=13,
        path_profile="starlink_v1",
    )
    res = run_sim(
        lambda: LeoAwareCCA(use_openslot=True, use_fill_gap=True, use_soft_ceil=False),
        cfg=cfg,
        n_flows=1,
    )
    assert res.cca_snapshots, "sim must attach CCA snapshots"
    snap = res.cca_snapshots[0]
    assert snap["cca"] == "LeoAware"
    assert snap["obs_acks"] > 0
    assert snap["obs_path_handovers"] == len(res.handovers), (
        snap["obs_path_handovers"],
        res.handovers,
    )
    for k in SNAPSHOT_FRAC_KEYS:
        v = snap[k]
        assert 0.0 <= v <= 1.0, (k, v)
    split = (
        snap["reprobe_ack_frac"]
        + snap["post_detect_ack_frac"]
        + snap["cruise_ack_frac"]
    )
    assert abs(split - 1.0) < 1e-9, split
    hook = leftover_scorecard_hook(
        leo_snaps=[snap],
        handovers=res.handovers,
        leo_gp=80.0,
        leo_p95=70.0,
    )
    assert hook["current_paid"] is False
    assert hook["path_handovers_mean"] == len(res.handovers)
    assert "H3_leftover_band_concentrated_in_real_ho" in hook["hypotheses"]
    assert "leftover_band_post_path_ho_frac" in snap
    print(
        "ok: short starlink_v1 leftover split "
        f"ho={len(res.handovers)} detect={snap['reconfigs_detected']} "
        f"cruise_band={snap['leftover_band_cruise_frac']:.3f} "
        f"post_band={snap['leftover_band_post_detect_frac']:.3f}"
    )


def test_detect_observe_is_read_only():
    cca = LeoAwareCCA()
    assert cca.use_fill_gap is False
    assert cca.use_soft_ceil is False
    before = (cca.cwnd, cca.mode, cca.reconfigs_detected, cca.score_threshold, cca.detect_cooldown)
    cca._observe_detect(5.0, "rtt_mad+rate_drop", 2.4)
    after = (cca.cwnd, cca.mode, cca.reconfigs_detected, cca.score_threshold, cca.detect_cooldown)
    assert after == before, (before, after)
    assert len(cca.obs_detect_events) == 1
    assert cca.obs_detect_events[0]["n_reasons"] == 2
    assert cca.obs_detect_far_path_ho == 1
    snap = cca.observability_snapshot()
    assert snap["obs_detect_far_path_ho"] == 1
    assert snap["obs_detect_events"][0]["primary"] == "rtt_mad"
    print("ok: detect observe is read-only (no cwnd / detect / threshold change)")


def test_shadow_gates_never_drop_loss_burst():
    assert "loss_burst" not in " ".join(SHADOW_GATE_NAMES)
    assert NEAR_HO_WINDOW_S == 1.4
    events = [
        {"t": 12.0, "reason": "loss_burst", "score": 1.4, "n_reasons": 1, "primary": "loss_burst"},
        {"t": 30.0, "reason": "rate_drop", "score": 1.35, "n_reasons": 1, "primary": "rate_drop"},
        {"t": 12.05, "reason": "rtt_mad+loss_burst", "score": 2.2, "n_reasons": 2, "primary": "rtt_mad"},
    ]
    hos = [12.0, 24.0]
    clf = classify_detect_overfire(events, hos)
    assert clf["near_n"] == 2
    assert clf["far_n"] == 1
    assert clf["ho_covered"] == 1
    # loss_burst-only still counts as a current detect; no shadow gate may
    # be defined as "drop loss_burst".
    assert clf["reason_counts"]["loss_burst"] == 2
    assert clf["shadow_gates"]["score_ge_2_0"]["reckless"] in (True, False)
    hook = detect_overfire_hook(
        leo_snaps=[{"seed": 13, "obs_detect_events": events, "handovers": hos}],
        handovers_by_seed={13: hos},
        leo_gp=82.45,
        leo_p95=76.26,
    )
    assert hook["current_paid"] is False
    assert hook["current_stays"] == "v3.17 FillGap"
    assert hook["softceil_decision"] == "REJECT"
    assert hook["gates"]["bump_current"] is False
    assert hook["bars"]["gp_mean"] == 75.0
    assert hook["bars"]["p95_mean"] == 138.8
    print("ok: shadow gates never drop loss_burst; hook never marks Current")


def test_short_starlink_v1_detect_events():
    cfg = LeoPathConfig(
        duration_s=8.0,
        handover_interval_s=4.0,
        handover_jitter_s=1.0,
        seed=13,
        path_profile="starlink_v1",
    )
    res = run_sim(
        lambda: LeoAwareCCA(use_openslot=True, use_fill_gap=True, use_soft_ceil=False),
        cfg=cfg,
        n_flows=1,
    )
    snap = res.cca_snapshots[0]
    assert "obs_detect_events" in snap
    assert len(snap["obs_detect_events"]) == snap["reconfigs_detected"], (
        snap["reconfigs_detected"],
        len(snap["obs_detect_events"]),
    )
    hook = detect_overfire_hook(
        leo_snaps=[{"seed": 13, **snap, "handovers": list(res.handovers)}],
        handovers_by_seed={13: list(res.handovers)},
        leo_gp=80.0,
        leo_p95=70.0,
    )
    assert hook["gates"]["gp_ge_75"] is True
    assert hook["gates"]["p95_le_138_8"] is True
    assert hook["gates"]["bump_current"] is False
    print(
        "ok: short starlink_v1 detect events "
        f"ho={len(res.handovers)} detect={snap['reconfigs_detected']} "
        f"events={len(snap['obs_detect_events'])}"
    )


def run_all() -> None:
    test_dual_gate_bars_frozen()
    test_scorecard_hook_never_marks_current()
    test_snapshot_is_read_only()
    test_path_ho_observe_does_not_reprobe()
    test_short_starlink_v1_leftover_split()
    test_detect_observe_is_read_only()
    test_shadow_gates_never_drop_loss_burst()
    test_short_starlink_v1_detect_events()
    print("ALL Starlink leftover observability tests passed")


if __name__ == "__main__":
    run_all()
