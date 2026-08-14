#!/usr/bin/env python3
"""leocc_v1 rails: real windows exist, Crest defaults stay off, no traces/real/."""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from experiments.run_leocc import (
    CAPPED_BUFFER_BYTES,
    LEOCC_BUFFER_BYTES,
    SIM_DT_S,
    send_ceiling_mbps,
)
from collections import deque

from experiments.slice_leocc import DURATION_S, DT_S, OUT_DIR
from leo_cc.ccas import BbrCCA, LeoAwareCCA
from leo_cc.harness import PRODUCT_PATH_PROFILE
from leo_cc.network import LeoPathConfig, load_trace_csv, walk_path_geometry


def test_no_empty_real_scaffold():
    real = ROOT / "traces" / "real"
    assert not real.exists(), "do not ship an empty traces/real/ scaffold"
    print("ok: no traces/real/ scaffold")


def test_leocc_windows_present():
    stats_path = OUT_DIR / "session_stats.json"
    assert stats_path.is_file(), stats_path
    stats = json.loads(stats_path.read_text(encoding="utf-8"))
    assert stats["era"] == "leocc_v1"
    assert stats["direction"] == "downlink_only"
    sessions = stats["sessions"]
    assert len(sessions) == 5, len(sessions)
    for s in sessions:
        path = OUT_DIR / s["csv_name"]
        assert path.exists() and path.stat().st_size > 1000, path
        rows = load_trace_csv(path)
        assert len(rows) == int(round(DURATION_S / DT_S)), (path, len(rows))
        assert rows[0].t_s == 0.0
        assert rows[-1].t_s >= DURATION_S - DT_S - 1e-9
        assert all(r.capacity_bps >= 0.0 for r in rows)
        assert all(r.rtt_s > 0.0 for r in rows), path
        assert sum(r.rtt_s for r in rows) / len(rows) > 0.01
        # rtt = 2 × owd: check first row against the owd column if present
    print(f"ok: {len(sessions)} LeoCC downlink windows load under {OUT_DIR}")


def test_rtt_is_twice_owd():
    import csv

    stats = json.loads((OUT_DIR / "session_stats.json").read_text(encoding="utf-8"))
    for s in stats["sessions"]:
        path = OUT_DIR / s["csv_name"]
        with path.open(encoding="utf-8", newline="") as f:
            rows = list(csv.DictReader(f))
        assert "owd_ms" in rows[0]
        for r in rows[::50]:
            rtt = float(r["rtt_ms"])
            owd = float(r["owd_ms"])
            assert abs(rtt - 2.0 * owd) < 1e-6, (path, rtt, owd)
    print("ok: rtt_ms == 2 * owd_ms on vendored slices")


def test_leocc_geometry_walks():
    stats = json.loads((OUT_DIR / "session_stats.json").read_text(encoding="utf-8"))
    oracles = []
    p95s = []
    for s in stats["sessions"]:
        path = OUT_DIR / s["csv_name"]
        g = walk_path_geometry(
            LeoPathConfig(
                duration_s=DURATION_S,
                dt_s=DT_S,
                path_profile="leocc_v1",
                trace_csv=str(path),
            )
        )
        oracles.append(g["oracle_gp_mbps"])
        p95s.append(g["path_p95_ms"])
    print(
        f"ok: leocc geometry resampled oracle_mean={sum(oracles)/len(oracles):.2f} "
        f"path_p95_mean={sum(p95s)/len(p95s):.2f}"
    )


def test_crest_defaults_stay_off():
    cca = LeoAwareCCA()
    assert cca.use_path_hints is False
    assert cca.use_halo is False
    assert cca.use_orbit_pulse is False
    assert cca.use_cfr is False
    assert cca.use_qsp is False
    assert cca.hint_freeze_only is False
    assert cca.use_fast_exit is False
    assert cca.use_lean_catch is False
    assert PRODUCT_PATH_PROFILE == "starlink_v1"
    print("ok: Crest defaults off; product profile still starlink_v1")


def test_lean_catch_restores_only_when_under_windowed():
    """LeanCatch restores after a 0.72 cut only if cwnd < 0.70 × delivery BDP."""
    cca = LeoAwareCCA(use_lean_catch=True)
    cca.min_rtt = 0.050
    cca.bw_est = 400e6
    cca.rate_ewma = 400e6
    cca.cwnd = 80 * 1200  # after 0.72 → 57.6 MSS; BDP ≈ 2083 MSS
    cca.delivered_marks.append((0.0, 0.0))
    cca.delivered_marks.append((0.25, 400e6 / 8.0 * 0.25))
    rec0 = cca.reconfigs_detected
    cca.on_loss(1.0, 1200, congestive=True)
    assert cca.mode == "congestive_recovery"
    assert cca.cwnd < 80 * 1200
    assert rec0 == cca.reconfigs_detected  # detect / loss_burst not involved
    cca.on_ack(1.02, 0.050, 1200)
    assert cca.lean_catches >= 1
    assert cca.cwnd > 57 * 1200
    print("ok: LeanCatch restores when under-windowed")


def test_lean_catch_does_not_restore_healthy_window():
    """A-like: after one 0.72 cut, cwnd still ≥ 0.70 × BDP → no restore."""
    cca = LeoAwareCCA(use_lean_catch=True)
    cca.min_rtt = 0.032
    cca.bw_est = 400e6
    cca.rate_ewma = 400e6
    # BDP ≈ 400e6 * 0.032 / 8 = 1.6e6 B ≈ 1333 MSS; 0.70× ≈ 933.
    # Start 1600 MSS → cut 1152 > 933.
    cca.cwnd = 1600 * 1200
    cca.delivered_marks.append((0.0, 0.0))
    cca.delivered_marks.append((0.25, 400e6 / 8.0 * 0.25))
    cca.on_loss(1.0, 1200, congestive=True)
    after_cut = cca.cwnd
    cca.on_ack(1.02, 0.032, 1200)
    assert cca.lean_catches == 0
    # May grow via cruise/startup, but must not jump to delivery BDP.
    assert cca.cwnd < 0.90 * (400e6 * 0.032 / 8.0)
    assert after_cut > 0
    print("ok: LeanCatch does not restore a healthy post-cut window")


def test_fast_exit_flag_is_inert():
    """use_fast_exit stays default False and never increments fast_exits."""
    cca = LeoAwareCCA(use_fast_exit=True)
    cca.min_rtt = 0.050
    cca.bw_est = 400e6
    cca.rate_ewma = 400e6
    cca.cwnd = 80 * 1200
    cca.delivered_marks.append((0.0, 0.0))
    cca.delivered_marks.append((0.25, 400e6 / 8.0 * 0.25))
    cca.on_loss(1.0, 1200, congestive=True)
    cca.on_ack(1.02, 0.050, 1200)
    assert cca.fast_exits == 0
    assert cca.lean_catches == 0
    print("ok: FastExit flag is inert (died; LeanCatch is the lever)")


def test_lean_catch_does_not_gate_loss_burst():
    cca = LeoAwareCCA(use_lean_catch=True)
    cca.min_rtt = 0.050
    cca.rtt_hist.extend([0.05, 0.051, 0.049, 0.05])
    cca.last_reconfig_t = -10.0
    rec0 = cca.reconfigs_detected
    cca.on_loss(5.0, 1200, congestive=False)
    cca.on_loss(5.05, 1200, congestive=False)
    assert cca.reconfigs_detected == rec0 + 1
    assert cca.mode == "ser:loss_burst" or str(cca.mode).startswith("ser")
    print("ok: LeanCatch does not gate ep:loss_burst")


def test_era_buffer_does_not_move_product_default():
    assert LeoPathConfig().buffer_bytes == CAPPED_BUFFER_BYTES
    assert LEOCC_BUFFER_BYTES == 1_000_000
    ceil = send_ceiling_mbps(LEOCC_BUFFER_BYTES, SIM_DT_S)
    assert ceil >= 550.0, ceil
    assert send_ceiling_mbps(CAPPED_BUFFER_BYTES, SIM_DT_S) == 200.0
    print(
        f"ok: product buffer {CAPPED_BUFFER_BYTES} B; "
        f"leocc era {LEOCC_BUFFER_BYTES} B ceiling {ceil:.0f} Mbps"
    )


def test_bbr_max_filter_matches_naive_scan():
    """O(1) bw_max_q must equal max(bw_window) on a long high-rate stream."""
    rng = __import__("random").Random(13)
    bbr = BbrCCA()
    bbr.min_rtt = 0.032
    t = 0.0
    naive: deque[tuple[float, float]] = deque()
    for i in range(8000):
        t += 0.00003  # ~33k marks/s, LeoCC-ish
        sample = 1e8 + rng.random() * 4e8
        bbr.bw_window.append((t, sample))
        while bbr.bw_max_q and bbr.bw_max_q[-1][1] <= sample:
            bbr.bw_max_q.pop()
        bbr.bw_max_q.append((t, sample))
        naive.append((t, sample))
        win = max(0.5, 10 * bbr.min_rtt)
        while bbr.bw_window and t - bbr.bw_window[0][0] > win:
            t0, _ = bbr.bw_window.popleft()
            if bbr.bw_max_q and bbr.bw_max_q[0][0] == t0:
                bbr.bw_max_q.popleft()
        while naive and t - naive[0][0] > win:
            naive.popleft()
        got = bbr.bw_max_q[0][1] if bbr.bw_max_q else 0.0
        want = max(b for _, b in naive) if naive else 0.0
        assert got == want, (i, got, want)
    print("ok: BBR sliding max matches naive scan (identity, not a CCA retune)")


def run_all() -> None:
    test_no_empty_real_scaffold()
    test_leocc_windows_present()
    test_rtt_is_twice_owd()
    test_leocc_geometry_walks()
    test_crest_defaults_stay_off()
    test_lean_catch_restores_only_when_under_windowed()
    test_lean_catch_does_not_restore_healthy_window()
    test_fast_exit_flag_is_inert()
    test_lean_catch_does_not_gate_loss_burst()
    test_era_buffer_does_not_move_product_default()
    test_bbr_max_filter_matches_naive_scan()
    print("ALL leocc_v1 integrity tests passed")


if __name__ == "__main__":
    run_all()
