"""
OrbCC-style in-network telemetry (simulation + optional consumer).

OrbCC (Valentine et al., arXiv:2508.19067) uses programmable-switch per-hop
state. This module provides:
  - OrbSignal dataclass (endpoint-visible echo of bottleneck fields)
  - utilization estimator matching the paper's U_i form
  - synthetic InNetworkTelemetry for the slot simulator

Deployment realism: full OrbCC needs in-path switches (or gateway assist).
When signals are absent, LeoAware degrades to endpoint (+ optional ASCENT).
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass
class OrbSignal:
    """Bottleneck-relevant in-network fields (receiver-echoed in real OrbCC)."""

    path_id: int
    bottleneck_u: float
    qlen_bytes: float
    bw_bps: float
    avg_rtt_s: float
    flow_cnt: int
    tx_bytes: float
    ts: float


def utilization(
    qlen_bytes: float,
    tx_rate_bps: float,
    avg_rtt_s: float,
    bw_bps: float,
) -> float:
    """
    OrbCC-style utilization:
      U = (qLen + txRate * avgRTT) / (bw * avgRTT)
    with rates in consistent units (bytes for queue, bps for rates).
    """
    if bw_bps <= 0 or avg_rtt_s <= 0:
        return 0.0
    # Convert bps * s -> bits, then /8 for bytes in flight estimate
    inflight_bytes = (tx_rate_bps * avg_rtt_s) / 8.0
    bdp_bytes = (bw_bps * avg_rtt_s) / 8.0
    if bdp_bytes <= 0:
        return 0.0
    return (qlen_bytes + inflight_bytes) / bdp_bytes


class InNetworkTelemetry:
    """
    Synthetic per-hop telemetry for LeoPath slots.

    path_id changes on reconfiguration (XOR of epoch-ish state).
    qLen mirrors shared bottleneck buffer; bw mirrors path capacity.
    """

    def __init__(self, switch_id: int = 0xA11):
        self.switch_id = switch_id & 0xFFFF
        self._last_tx_bytes = 0.0
        self._last_ts = 0.0
        self._cum_tx_bytes = 0.0
        self._last_path_id: Optional[int] = None
        self._avg_rtt_s = 0.04

    def on_drain(self, bytes_drained: float) -> None:
        self._cum_tx_bytes += max(0.0, bytes_drained)

    def sample(
        self,
        t: float,
        *,
        epoch: int,
        capacity_bps: float,
        rtt_s: float,
        qlen_bytes: float,
        flow_cnt: int = 1,
        reconfigured: bool = False,
    ) -> OrbSignal:
        # pathID: stable per epoch (must NOT one-shot XOR on reconfig flag -
        # that flipped pathID for a single slot then back, double-firing REPROBE).
        path_id = (self.switch_id ^ (int(epoch) & 0xFFFF) ^ 0xA11CE) & 0xFFFFFFFF
        _ = reconfigured  # reserved for telemetry logs; identity is epoch

        # EWMA of path RTT as cwnd-weighted proxy
        alpha = 0.2
        if self._avg_rtt_s <= 0:
            self._avg_rtt_s = rtt_s
        else:
            self._avg_rtt_s = (1 - alpha) * self._avg_rtt_s + alpha * max(rtt_s, 1e-4)

        # Instant tx rate from drain marks
        tx_rate = 0.0
        if self._last_ts > 0 and t > self._last_ts:
            dt = t - self._last_ts
            dbytes = self._cum_tx_bytes - self._last_tx_bytes
            tx_rate = (dbytes * 8.0) / max(dt, 1e-6)
        self._last_tx_bytes = self._cum_tx_bytes
        self._last_ts = t
        self._last_path_id = path_id

        u = utilization(qlen_bytes, tx_rate, self._avg_rtt_s, capacity_bps)
        return OrbSignal(
            path_id=path_id,
            bottleneck_u=u,
            qlen_bytes=float(qlen_bytes),
            bw_bps=float(capacity_bps),
            avg_rtt_s=float(self._avg_rtt_s),
            flow_cnt=max(1, int(flow_cnt)),
            tx_bytes=self._cum_tx_bytes,
            ts=t,
        )
