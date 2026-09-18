"""Congestive enqueue drop must not free bytes_in_flight that were never taken."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from leo_cc.ccas import CubicCCA, MSS
from leo_cc.network import LeoPathConfig
from leo_cc.sim import run_sim


class TrackingCubic(CubicCCA):
    name = "TrackingCubic"

    def __init__(self):
        super().__init__()
        self.sent_events = 0
        self.loss_events = 0

    def on_sent(self, n: int) -> None:
        super().on_sent(n)
        self.sent_events += 1

    def on_loss(self, t: float, bytes_lost: int, congestive: bool) -> None:
        super().on_loss(t, bytes_lost, congestive)
        self.loss_events += 1


def test_unit_enqueue_loss_preserves_prior_inflight():
    """Prior inflight MSS must survive an enqueue-style sent-then-lost pair."""
    c = CubicCCA()
    c.on_sent(MSS)
    assert c.bytes_in_flight == MSS
    c.on_sent(MSS)
    c.on_loss(0.1, MSS, congestive=True)
    assert c.bytes_in_flight == MSS, (
        f"expected prior inflight preserved, got {c.bytes_in_flight}"
    )


def test_bug_enqueue_loss_without_on_sent_frees_prior_inflight():
    """Document the pre-fix bug: on_loss alone frees never-sent bytes."""
    c = CubicCCA()
    c.on_sent(MSS)
    assert c.bytes_in_flight == MSS
    # Old sim path: on_loss without on_sent
    c.on_loss(0.1, MSS, congestive=True)
    assert c.bytes_in_flight == 0, "precondition: bare on_loss frees prior inflight"


def test_sim_congestive_enqueue_accounts_sent():
    held = {"cca": None}

    def factory():
        c = TrackingCubic()
        held["cca"] = c
        return c

    cfg = LeoPathConfig(
        duration_s=2.0,
        dt_s=0.01,
        seed=7,
        buffer_bytes=MSS * 2,
        capacity_min_bps=80e6,
        capacity_max_bps=80e6,
        handover_interval_s=10.0,
        terrestrial=True,
    )
    run_sim(factory, cfg=cfg, n_flows=1, path_hint_mode="none")
    cca = held["cca"]
    assert cca is not None
    assert cca.loss_events > 0, "expected congestive enqueue losses"
    assert cca.bytes_in_flight >= 0
    assert cca.sent_events >= cca.loss_events, (
        f"sent={cca.sent_events} loss={cca.loss_events}: enqueue loss without on_sent"
    )


if __name__ == "__main__":
    test_unit_enqueue_loss_preserves_prior_inflight()
    test_bug_enqueue_loss_without_on_sent_frees_prior_inflight()
    test_sim_congestive_enqueue_accounts_sent()
    print("ok: congestive enqueue inflight")
