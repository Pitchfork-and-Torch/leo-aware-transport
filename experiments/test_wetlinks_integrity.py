#!/usr/bin/env python3
"""WetLinks CSV lock rails: real windows exist, Crest defaults stay off."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from experiments.run_wetlinks import (
    CAPPED_BUFFER_BYTES,
    SIM_DT_S,
    WETLINKS_BUFFER_BYTES,
    send_ceiling_mbps,
)
from experiments.slice_wetlinks import DURATION_S, DT_S, OUT_DIR, WINDOW_SPECS
from leo_cc.ccas import LeoAwareCCA
from leo_cc.harness import PRODUCT_PATH_PROFILE
from leo_cc.network import LeoPathConfig, load_trace_csv, walk_path_geometry


def test_no_empty_real_scaffold():
    real = ROOT / "traces" / "real"
    assert not real.exists(), "do not ship an empty traces/real/ scaffold"
    print("ok: no traces/real/ scaffold")


def test_wetlinks_windows_present():
    assert OUT_DIR.is_dir(), OUT_DIR
    for wid, _, _ in WINDOW_SPECS:
        path = OUT_DIR / f"{wid}.csv"
        assert path.exists() and path.stat().st_size > 1000, path
        rows = load_trace_csv(path)
        assert len(rows) == int(round(DURATION_S / DT_S)), (path, len(rows))
        assert rows[0].t_s == 0.0
        assert rows[-1].t_s >= DURATION_S - DT_S - 1e-9
        assert all(r.capacity_bps > 1e6 for r in rows)
        assert all(r.rtt_s > 0.0 for r in rows)
    print(f"ok: {len(WINDOW_SPECS)} WetLinks windows load under {OUT_DIR}")


def test_wetlinks_geometry_walks():
    oracles = []
    p95s = []
    for wid, _, _ in WINDOW_SPECS:
        path = OUT_DIR / f"{wid}.csv"
        g = walk_path_geometry(
            LeoPathConfig(
                duration_s=DURATION_S,
                dt_s=DT_S,
                path_profile="wetlinks_v1",
                trace_csv=str(path),
            )
        )
        assert g["trace_csv"] == str(path)
        oracles.append(g["oracle_gp_mbps"])
        p95s.append(g["path_p95_ms"])
    print(
        f"ok: wetlinks geometry oracle_mean={sum(oracles)/len(oracles):.2f} "
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
    assert cca.use_openslot is False
    assert PRODUCT_PATH_PROFILE == "starlink_v1"
    print("ok: Crest defaults off; product profile still starlink_v1")


def test_uncap_buffer_does_not_move_product_default():
    assert LeoPathConfig().buffer_bytes == CAPPED_BUFFER_BYTES
    assert WETLINKS_BUFFER_BYTES == 1_000_000
    ceil = send_ceiling_mbps(WETLINKS_BUFFER_BYTES, SIM_DT_S)
    assert ceil >= 450.0, ceil
    assert send_ceiling_mbps(CAPPED_BUFFER_BYTES, SIM_DT_S) == 200.0
    print(
        f"ok: product buffer {CAPPED_BUFFER_BYTES} B; "
        f"WetLinks uncap {WETLINKS_BUFFER_BYTES} B ceiling {ceil:.0f} Mbps"
    )


def run_all() -> None:
    test_no_empty_real_scaffold()
    test_wetlinks_windows_present()
    test_wetlinks_geometry_walks()
    test_crest_defaults_stay_off()
    test_uncap_buffer_does_not_move_product_default()
    print("ALL WetLinks integrity tests passed")


if __name__ == "__main__":
    run_all()
