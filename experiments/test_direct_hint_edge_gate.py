#!/usr/bin/env python3
"""direct path_hint_mode must edge-gate like ascent_d (no per-slot freeze hammer)."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from leo_cc.ccas import LeoAwareCCA
from leo_cc.harness import apply_profile, resolve_path_profile
from leo_cc.network import LeoPathConfig
from leo_cc.sim import run_sim


def _count_freeze_ingests(mode: str, duration_s: float = 20.0, seed: int = 13) -> int:
    counts = {"freeze": 0}
    orig = LeoAwareCCA.on_path_hint

    def wrapped(self, t, reconfigured, **kw):
        fa = kw.get("freeze_active")
        fr = kw.get("freeze_remaining_s")
        if self.use_path_hints and (fa or (fr is not None and fr > 0)):
            counts["freeze"] += 1
        return orig(self, t, reconfigured, **kw)

    LeoAwareCCA.on_path_hint = wrapped  # type: ignore[method-assign]
    try:
        cfg = LeoPathConfig(duration_s=duration_s, handover_interval_s=5.0, seed=seed)
        cfg = apply_profile(cfg, resolve_path_profile("starlink_v1"))
        run_sim(
            lambda: LeoAwareCCA(use_path_hints=True),
            cfg=cfg,
            n_flows=1,
            path_hint_mode=mode,
        )
    finally:
        LeoAwareCCA.on_path_hint = orig  # type: ignore[method-assign]
    return counts["freeze"]


def test_direct_matches_ascent_d_freeze_edges() -> None:
    direct_n = _count_freeze_ingests("direct")
    ascent_n = _count_freeze_ingests("ascent_d")
    plain_n = _count_freeze_ingests("ascent_plain")
    # Pre-fix direct was ~123 freeze ingests over 20s; edge gate is single digits.
    assert direct_n < 30, direct_n
    assert direct_n == ascent_n == plain_n, (direct_n, ascent_n, plain_n)
    assert direct_n > 0
    print(f"ok: direct/ascent_d/ascent_plain freeze edges match n={direct_n}")


def test_endpoint_default_still_ignores_hints() -> None:
    n = {"hints": 0}
    orig = LeoAwareCCA.on_path_hint

    def wrapped(self, t, reconfigured, **kw):
        n["hints"] += 1
        return orig(self, t, reconfigured, **kw)

    LeoAwareCCA.on_path_hint = wrapped  # type: ignore[method-assign]
    try:
        cfg = LeoPathConfig(duration_s=5.0, handover_interval_s=2.0, seed=7)
        cfg = apply_profile(cfg, resolve_path_profile("starlink_v1"))
        # Constructor default use_path_hints=False; direct still may call, but
        # CCA must no-op. Count entries into on_path_hint (still invoked).
        run_sim(lambda: LeoAwareCCA(), cfg=cfg, n_flows=1, path_hint_mode="direct")
    finally:
        LeoAwareCCA.on_path_hint = orig  # type: ignore[method-assign]
    # Edge-gated: a few calls, not every slot (500).
    assert 0 < n["hints"] < 40, n["hints"]
    print(f"ok: endpoint direct calls edge-gated n={n['hints']}")


if __name__ == "__main__":
    test_direct_matches_ascent_d_freeze_edges()
    test_endpoint_default_still_ignores_hints()
    print("ALL direct-hint edge-gate tests passed")
