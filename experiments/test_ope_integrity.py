#!/usr/bin/env python3
"""OPE path-identity + frozen soft-QIR + excess-RTT diagnostic checks."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from leo_cc.ccas import BbrCCA, CubicCCA, LeoAwareCCA
from leo_cc.metrics import summarize_result
from leo_cc.network import LeoPath, LeoPathConfig, walk_path_geometry
from leo_cc.sim import SOFT_QIR_ALPHA, SOFT_QIR_CAP_S, run_sim


def test_soft_qir_frozen():
    assert SOFT_QIR_ALPHA == 0.20, SOFT_QIR_ALPHA
    assert SOFT_QIR_CAP_S == 0.025, SOFT_QIR_CAP_S
    print("ok: soft-QIR α frozen at 0.20 / 25ms cap")


def _assert_ope_path_identity(cfg: LeoPathConfig, label: str) -> None:
    """Same seed ⇒ identical HO / path-RTT timeline across CCAs (OPE)."""
    logs = {}
    hos = {}
    for name, cls in (("CUBIC", CubicCCA), ("BBR", BbrCCA), ("LeoAware", LeoAwareCCA)):
        res = run_sim(cls, cfg=cfg, n_flows=1)
        logs[name] = list(res.flows[0].rtt)
        hos[name] = list(res.handovers)
    assert hos["CUBIC"] == hos["BBR"] == hos["LeoAware"], (label, hos)
    assert logs["CUBIC"] == logs["BBR"] == logs["LeoAware"], label
    print(f"ok: OPE path identity ({label})  n_ho={len(hos['BBR'])}  rtt_samples={len(logs['BBR'])}")


def test_ope_path_identity():
    cfg = LeoPathConfig(
        duration_s=12.0,
        handover_interval_s=4.0,
        handover_jitter_s=1.0,
        seed=13,
    )
    _assert_ope_path_identity(cfg, "ope_v36 default")


def test_starlink_v1_ope_path_identity():
    """Kill condition: starlink_v1 must not be a Leo-asymmetric cherry-pick vs BBR."""
    cfg = LeoPathConfig(
        duration_s=12.0,
        handover_interval_s=4.0,
        handover_jitter_s=1.0,
        seed=13,
        path_profile="starlink_v1",
    )
    _assert_ope_path_identity(cfg, "starlink_v1")


def test_ope_v36_geometry_stable():
    """Default profile must not silently change orbital draws vs v3.6/v3.7."""
    cfg = LeoPathConfig(
        duration_s=90,
        handover_interval_s=12,
        handover_jitter_s=4,
        seed=13,
        path_profile="ope_v36",
    )
    path = LeoPath(cfg)
    first_ho_rtt = None
    while path.t < 90.0:
        st = path.step()
        if st.reconfigured and first_ho_rtt is None:
            first_ho_rtt = st.rtt_s
            first_ho_t = path.t - cfg.dt_s
            first_cap = st.capacity_bps
            break
    else:
        raise AssertionError("no handover on seed 13 / 90s")
    # Frozen golden from ope_v36 draw sequence (seed 13).
    assert abs(first_ho_t - 10.08) < 1e-9, first_ho_t
    assert abs(first_ho_rtt - 0.102968) < 1e-5, first_ho_rtt
    assert abs(first_cap - 102873161.7) < 1.0, first_cap
    print(
        f"ok: ope_v36 seed13 first HO t={first_ho_t:.3f}s "
        f"rtt={first_ho_rtt*1000:.1f}ms cap={first_cap/1e6:.1f}Mbps"
    )


def test_ope_v36_absolute_bars_infeasible():
    """Guard: research generative default must not silently be raised to fake 75/138.8."""
    oracles = []
    p95s = []
    for seed in (13, 7, 42, 99, 123):
        g = walk_path_geometry(
            LeoPathConfig(
                duration_s=90,
                handover_interval_s=12,
                handover_jitter_s=4,
                seed=seed,
            )
        )
        oracles.append(g["oracle_gp_mbps"])
        p95s.append(g["path_p95_ms"])
    oracle_mean = sum(oracles) / 5
    p95_mean = sum(p95s) / 5
    assert oracle_mean < 75.0, oracle_mean
    assert p95_mean > 138.8, p95_mean
    print(
        f"ok: ope_v36 geometry still forbids absolute bars "
        f"(oracle {oracle_mean:.2f} / path p95 {p95_mean:.2f})"
    )


def test_excess_rtt_diagnostic():
    cfg = LeoPathConfig(duration_s=8.0, handover_interval_s=20.0, seed=19, terrestrial=True)
    res = run_sim(LeoAwareCCA, cfg=cfg, n_flows=1)
    m = summarize_result(res)[0]
    assert res.soft_qir_alpha == 0.20
    assert m.p95_path_rtt_s == m.p95_path_rtt_s  # not NaN
    assert m.p95_excess_rtt_s >= 0.0
    assert m.mean_excess_rtt_s >= 0.0
    # Terrestrial path base is 40ms; ACK p95 is path + QIR (≤25ms).
    assert abs(m.p95_path_rtt_s - 0.04) < 1e-6, m.p95_path_rtt_s
    assert m.p95_rtt_s >= m.p95_path_rtt_s
    print(
        f"ok: excess-RTT terr p95={m.p95_rtt_s*1000:.1f} "
        f"path={m.p95_path_rtt_s*1000:.1f} excess={m.p95_excess_rtt_s*1000:.1f}"
    )


def test_starlink_profile_is_opt_in():
    """starlink_v1 must not change frozen ope_v36 generative identity."""
    a = walk_path_geometry(
        LeoPathConfig(duration_s=30, handover_interval_s=12, handover_jitter_s=4, seed=42)
    )
    b = walk_path_geometry(
        LeoPathConfig(
            duration_s=30,
            handover_interval_s=12,
            handover_jitter_s=4,
            seed=42,
            path_profile="ope_v36",
        )
    )
    c = walk_path_geometry(
        LeoPathConfig(
            duration_s=30,
            handover_interval_s=12,
            handover_jitter_s=4,
            seed=42,
            path_profile="starlink_v1",
        )
    )
    assert a["path_p95_ms"] == b["path_p95_ms"]
    assert a["handovers"] == b["handovers"]
    assert c["path_p95_ms"] != a["path_p95_ms"] or c["mean_cap_mbps"] != a["mean_cap_mbps"]
    print("ok: starlink_v1 is a distinct profile; ope_v36 generative default unchanged")


def test_starlink_v1_geometry_allows_absolute_bars():
    """Product-lock path must make gp≥75 AND p95≤138.8 geometrically possible."""
    from leo_cc.harness import PRODUCT_GP_BAR, PRODUCT_P95_BAR, PRODUCT_PATH_PROFILE, PRODUCT_SEEDS

    assert PRODUCT_PATH_PROFILE == "starlink_v1"
    oracles = []
    p95s = []
    for seed in PRODUCT_SEEDS:
        g = walk_path_geometry(
            LeoPathConfig(
                duration_s=90,
                handover_interval_s=12,
                handover_jitter_s=4,
                seed=seed,
                path_profile=PRODUCT_PATH_PROFILE,
            )
        )
        oracles.append(g["oracle_gp_mbps"])
        p95s.append(g["path_p95_ms"])
    oracle_mean = sum(oracles) / len(oracles)
    p95_mean = sum(p95s) / len(p95s)
    assert oracle_mean >= PRODUCT_GP_BAR, oracle_mean
    assert p95_mean <= PRODUCT_P95_BAR, p95_mean
    print(
        f"ok: starlink_v1 geometry allows absolute bars "
        f"(oracle {oracle_mean:.2f} / path p95 {p95_mean:.2f})"
    )


def test_loss_burst_not_gated():
    """v3.9 must still REPROBE on ep:loss_burst (primary hop detector)."""
    cca = LeoAwareCCA()
    cca.min_rtt = 0.05
    cca.rtt_hist.extend([0.05, 0.051, 0.049, 0.05])
    cca.last_reconfig_t = -10.0
    rec0 = cca.reconfigs_detected
    t = 5.0
    cca.on_loss(t, 1200, congestive=False)
    cca.on_loss(t + 0.05, 1200, congestive=False)
    assert cca.reconfigs_detected == rec0 + 1, (
        cca.reconfigs_detected,
        cca.mode,
    )
    assert cca.mode == "ser:loss_burst" or cca.mode.startswith("ser"), cca.mode
    print("ok: ep:loss_burst still enters SER/REPROBE")


def test_ca_does_not_fire_during_reprobe():
    cca = LeoAwareCCA()
    cca.min_rtt = 0.05
    cca.bw_est = 80e6
    cca.reprobe_until = 10.0
    cca.rtt_hist.extend([0.05] * 20)
    hit = cca._crest_hit(t=1.0, rtt_s=0.09, delay_ratio=1.8)
    assert hit is False
    print("ok: CA-hard does not abort during REPROBE")


def test_openslot_default_false():
    cca = LeoAwareCCA()
    assert cca.use_openslot is False
    print("ok: OpenSlot default False")


def test_openslot_does_not_gate_loss_burst():
    cca = LeoAwareCCA(use_openslot=True)
    cca.min_rtt = 0.05
    cca.rtt_hist.extend([0.05, 0.051, 0.049, 0.05])
    cca.last_reconfig_t = -10.0
    rec0 = cca.reconfigs_detected
    t = 5.0
    cca.on_loss(t, 1200, congestive=False)
    cca.on_loss(t + 0.05, 1200, congestive=False)
    assert cca.reconfigs_detected == rec0 + 1, (cca.reconfigs_detected, cca.mode)
    assert cca.mode == "ser:loss_burst" or str(cca.mode).startswith("ser"), cca.mode
    print("ok: OpenSlot does not gate ep:loss_burst")


def test_openslot_unbinds_only_when_clean():
    cca = LeoAwareCCA(use_openslot=True)
    cca.min_rtt = 0.05
    cca.rtt_hist.extend([0.05] * 8)
    cca.cwnd = 80 * 1200
    cca.bytes_in_flight = 10 * 1200
    cca.pacing_rate_bps = 10e6
    cca._last_pace_t = 1.0
    cca._pace_credit = 1200.0
    clean = cca.can_send(1.02)
    assert clean >= 60 * 1200, clean
    assert cca.openslot_releases >= 1
    cca.rtt_hist.append(0.09)  # delay_ratio 1.8
    cca._pace_credit = 1200.0
    cca._last_pace_t = 2.0
    dirty = cca.can_send(2.001)
    assert dirty < clean, (dirty, clean)
    assert dirty <= 8 * 1200, dirty
    print("ok: OpenSlot unbinds only on delay-clean slots")


def run_all() -> None:
    test_soft_qir_frozen()
    test_ope_path_identity()
    test_starlink_v1_ope_path_identity()
    test_ope_v36_geometry_stable()
    test_ope_v36_absolute_bars_infeasible()
    test_excess_rtt_diagnostic()
    test_starlink_profile_is_opt_in()
    test_starlink_v1_geometry_allows_absolute_bars()
    test_loss_burst_not_gated()
    test_ca_does_not_fire_during_reprobe()
    test_openslot_default_false()
    test_openslot_does_not_gate_loss_burst()
    test_openslot_unbinds_only_when_clean()
    print("ALL OPE integrity tests passed")


if __name__ == "__main__":
    run_all()
