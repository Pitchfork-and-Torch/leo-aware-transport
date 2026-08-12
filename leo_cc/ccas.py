"""
Congestion control algorithms (sender-side, modular).

- CubicCCA: classic CUBIC-inspired window growth (simplified for research sim).
- BbrCCA: BBR-family pacing/bandwidth probing approximation (not bit-exact BBRv3).
- LeoAwareCCA: LEO-aware controller  -  detects reconfigurations, resets stale
  min-RTT / bandwidth samples, re-probes carefully after path changes.
"""
from __future__ import annotations

from dataclasses import dataclass
from collections import deque
from typing import Deque, Optional, TYPE_CHECKING
import math

if TYPE_CHECKING:
    from leo_cc.orb_signals import OrbSignal


MSS = 1200  # bytes, ~QUIC-ish payload unit


@dataclass
class AckSample:
    t: float
    rtt_s: float
    bytes_acked: int
    lost: int = 0


@dataclass
class CCAState:
    cwnd_bytes: float
    pacing_rate_bps: float
    ssthresh_bytes: float
    min_rtt_s: float
    bw_est_bps: float
    mode: str = "startup"
    epoch: int = 0


class BaseCCA:
    name: str = "base"

    def __init__(self, init_cwnd_mss: int = 10):
        self.cwnd = init_cwnd_mss * MSS
        self.ssthresh = float("inf")
        self.min_rtt = float("inf")
        self.bw_est = 0.0
        self.t_last = 0.0
        self.bytes_in_flight = 0
        self.mode = "startup"
        self.pacing_rate_bps = 0.0
        self._pace_credit = 0.0
        self._pace_t = 0.0

    def on_ack(self, t: float, rtt_s: float, bytes_acked: int, lost: int = 0) -> None:
        raise NotImplementedError

    def on_loss(self, t: float, bytes_lost: int, congestive: bool) -> None:
        raise NotImplementedError

    def on_path_hint(
        self,
        t: float,
        reconfigured: bool,
        *,
        capacity_bps: float | None = None,
        rtt_s: float | None = None,
        epoch: int | None = None,
        freeze_remaining_s: float | None = None,
        freeze_active: bool | None = None,
        next_capacity_bps: float | None = None,
    ) -> None:
        """Optional network / ASCENT-style path hint (not required for endpoint detection)."""
        pass

    def on_ecn(self, t: float, ce_count: int = 1) -> None:
        """Optional ECN Congestion Experienced marks (production hook)."""
        pass

    def on_orb_signal(self, t: float, sig: "OrbSignal") -> None:
        """Optional OrbCC-style in-network telemetry (no-op by default)."""
        pass

    def can_send(self, t: float) -> int:
        room = max(0.0, self.cwnd - self.bytes_in_flight)
        return int(room // MSS) * MSS

    def on_sent(self, n: int) -> None:
        self.bytes_in_flight += n

    def on_delivered(self, n: int) -> None:
        self.bytes_in_flight = max(0, self.bytes_in_flight - n)

    def state(self) -> CCAState:
        pace = (
            self.pacing_rate_bps
            if self.pacing_rate_bps > 0
            else (self.bw_est if self.bw_est > 0 else (self.cwnd * 8 / max(self.min_rtt, 1e-3)))
        )
        return CCAState(
            cwnd_bytes=self.cwnd,
            pacing_rate_bps=pace,
            ssthresh_bytes=self.ssthresh if self.ssthresh < 1e18 else -1,
            min_rtt_s=self.min_rtt if self.min_rtt < 1e17 else -1,
            bw_est_bps=self.bw_est,
            mode=self.mode,
        )


class CubicCCA(BaseCCA):
    """Simplified CUBIC: W(t) = C*(t-K)^3 + W_max after reduction."""

    name = "CUBIC"
    C = 0.4
    beta = 0.7

    def __init__(self, **kw):
        super().__init__(**kw)
        self.w_max = self.cwnd
        self.epoch_start = 0.0
        self.k = 0.0
        self.origin_point = 0.0

    def _cubic_cwnd(self, t: float) -> float:
        if self.epoch_start <= 0:
            return self.cwnd
        elapsed = max(0.0, t - self.epoch_start)
        return self.C * (elapsed - self.k) ** 3 + self.origin_point

    def on_ack(self, t: float, rtt_s: float, bytes_acked: int, lost: int = 0) -> None:
        self.min_rtt = min(self.min_rtt, rtt_s)
        self.on_delivered(bytes_acked)
        if self.cwnd < self.ssthresh:
            self.cwnd += bytes_acked  # slow start
            self.mode = "slow_start"
            return
        self.mode = "cubic"
        target = self._cubic_cwnd(t)
        if target > self.cwnd:
            self.cwnd += (target - self.cwnd) / self.cwnd * MSS
        else:
            self.cwnd += MSS * (MSS / self.cwnd)
        # bandwidth sample
        if rtt_s > 0:
            sample = bytes_acked * 8 / rtt_s
            self.bw_est = 0.9 * self.bw_est + 0.1 * sample if self.bw_est > 0 else sample

    def on_loss(self, t: float, bytes_lost: int, congestive: bool) -> None:
        self.on_delivered(bytes_lost)
        # CUBIC reacts to loss as congestion (problem on LEO non-congestive loss)
        self.w_max = self.cwnd
        self.ssthresh = max(2 * MSS, self.cwnd * self.beta)
        self.cwnd = self.ssthresh
        self.origin_point = self.cwnd
        self.epoch_start = t
        self.k = ((self.w_max * (1 - self.beta)) / self.C) ** (1 / 3)
        self.mode = "recovery"


class BbrCCA(BaseCCA):
    """
    BBR-family approximation: estimate bw and min_rtt; target BDP-sized cwnd.
    Educational model (not a bit-exact BBRv2/v3 port). Uses delivery-rate
    samples over a sliding time window rather than per-packet RTT ratios.
    """

    name = "BBRv3approx"

    def __init__(self, **kw):
        super().__init__(**kw)
        self.bw_window: Deque[tuple[float, float]] = deque()  # (t, bps)
        self.delivered_marks: Deque[tuple[float, float]] = deque()  # (t, cum_bytes)
        self.cum_delivered = 0.0
        self.min_rtt_stamp = 0.0
        self.cycle = 0
        self.cycle_t = 0.0
        self.pacing_gain = 2.77  # startup-ish
        self.cwnd_gain = 2.0
        self.started = False

    def _update_bw(self, t: float, bytes_acked: int) -> None:
        self.cum_delivered += bytes_acked
        self.delivered_marks.append((t, self.cum_delivered))
        # Keep ~max(10*min_rtt, 0.5s) of marks
        win = max(0.5, 10 * (self.min_rtt if self.min_rtt < 1e17 else 0.05))
        while self.delivered_marks and t - self.delivered_marks[0][0] > win:
            self.delivered_marks.popleft()
        if len(self.delivered_marks) >= 2:
            t0, b0 = self.delivered_marks[0]
            t1, b1 = self.delivered_marks[-1]
            dt = t1 - t0
            if dt > 1e-4:
                sample = (b1 - b0) * 8.0 / dt
                self.bw_window.append((t, sample))
        while self.bw_window and t - self.bw_window[0][0] > win:
            self.bw_window.popleft()
        if self.bw_window:
            # max filter (BBR-style)
            self.bw_est = max(b for _, b in self.bw_window)

    def _bdp(self) -> float:
        if self.min_rtt >= 1e17 or self.bw_est <= 0:
            return 10 * MSS
        return self.bw_est * self.min_rtt / 8.0

    def on_ack(self, t: float, rtt_s: float, bytes_acked: int, lost: int = 0) -> None:
        self.on_delivered(bytes_acked)
        if rtt_s < self.min_rtt:
            self.min_rtt = rtt_s
            self.min_rtt_stamp = t
        elif self.min_rtt >= 1e17:
            self.min_rtt = rtt_s
            self.min_rtt_stamp = t
        self._update_bw(t, bytes_acked)

        # Startup: grow aggressively until bw estimate plateaus
        if not self.started or self.bw_est <= 0:
            self.cwnd += bytes_acked * 2
            self.mode = "startup"
            if self.bw_est > 1e6:
                self.started = True
                self.cycle_t = t
            return

        # Probe cycle every ~8 RTTs (simplified)
        rtt_ref = max(self.min_rtt, 0.02)
        if t - self.cycle_t > 8 * rtt_ref:
            self.cycle = (self.cycle + 1) % 8
            self.cycle_t = t
            self.pacing_gain = 1.25 if self.cycle == 0 else (0.75 if self.cycle == 1 else 1.0)

        bdp = self._bdp()
        gain = self.cwnd_gain * min(self.pacing_gain, 1.25)
        # Cap to a realistic multiple of BDP so multi-flow does not implode
        self.cwnd = max(4 * MSS, min(gain * bdp, 4.0 * max(bdp, 10 * MSS)))

        # Stale min-RTT is the classic LEO failure mode for BBR-class controllers
        if t - self.min_rtt_stamp > 10.0:
            self.mode = "stale_min_rtt"
            # Mild aging: inflate min_rtt slightly so BDP is not stuck low forever
            # (still wrong vs full invalidation - LeoAware contrast)
            self.min_rtt *= 1.02
            self.min_rtt_stamp = t
        else:
            self.mode = "probe" if self.pacing_gain != 1.0 else "cruise"

    def on_loss(self, t: float, bytes_lost: int, congestive: bool) -> None:
        self.on_delivered(bytes_lost)
        # Classic BBR largely ignores loss; slight shrink only on heavy congestive loss
        if congestive and bytes_lost >= MSS:
            self.cwnd = max(4 * MSS, self.cwnd * 0.95)
        self.mode = "loss_ignored"


from leo_cc.leo_aware import LeoAwareCCA  # noqa: E402  # v3.4.1 module split for review

__all__ = [
    "MSS",
    "AckSample",
    "CCAState",
    "BaseCCA",
    "CubicCCA",
    "BbrCCA",
    "LeoAwareCCA",
]
