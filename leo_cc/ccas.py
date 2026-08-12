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


class LeoAwareCCA(BaseCCA):
    """
    LeoAware v3.3-C - hybrid fuse + DTCE (OrbitStack).

    Endpoint-first (works with zero network cooperation). Optional ASCENT /
    path hints accelerate reconfig handling when available. Optional OrbCC-style
    in-network signals for high-confidence pathID + utilization.

    v3 additions:
      - Multi-seed HO objective: reclaim capacity faster (prior-bw seed after hop)
      - fair_mode: delay-based AIMD friendliness for multi-flow
      - ASCENT freeze windows: hold growth during freeze_remaining_s, then REPROBE
      - Dual-signal gate reduces false REPROBE without starving true hops

    v3.1 additions:
      - Path-aware sizing RTT / delay_ratio (no death spiral on stale min_rtt)
      - Soft min_rtt age every ~6s (raise toward recent min, no full REPROBE)
      - Post-hop max-filter reclaim + decaying prior floor
      - Startup detect warmup; richer freeze pre-position to next_capacity
      - Honest freeze-lead next_capacity peek in path model (non-consuming)

    v3.2 additions:
      - ASCENT-D integrity path (fail-closed ingest via ascent_path_hint module)
      - Optional on_orb_signal: pathID reconfig + utilization AIMD (OrbCC hybrid)
      - Confidence-conditioned REPROBE cuts (endpoint vs ASCENT-D vs Orb pathID)
      - Mobility taxonomy reinforced when in-network qLen is near empty

    v3.3-A hybrid fuse (PR A):
      - _should_suppress_orb_reprobe: assist 2.0s / freeze / REPROBE / detect_cooldown
      - Hybrid: never util-MD; Orb pathID REPROBE only when not suppressed
      - Orb-only util-MD: U high AND qlen non-trivial outside freeze/reprobe
      - _enter_reprobe refuses orb* while suppressed; endpoint cut stays 0.58
      - Public suite default remains endpoint-only

    v3.3-C DTCE (PR C):
      - cruise_bw_ring / cruise_rtt_ring (maxlen 8) capture stable cruise only
      - post-hop race: lo~p25 / hi~p75 envelope for ~1.5s; continuity reclaims hi
      - redraw-down abandons envelope; fair_mode skips race
      - rings NOT cleared on REPROBE (cross-epoch memory only)

    Related: LeoCC response-interval outliers; SaTCP freeze; OrbCC pathID/U;
    BBR delivery-rate without stale min-RTT across epochs.
    """

    name = "LeoAware"

    def __init__(
        self,
        use_path_hints: bool = False,
        fair_mode: bool = False,
        use_orb_signals: bool = False,
        orb_eta: float = 0.95,
        **kw,
    ):
        super().__init__(**kw)
        self.use_path_hints = use_path_hints
        self.fair_mode = fair_mode
        self.use_orb_signals = use_orb_signals
        self.orb_eta = float(orb_eta)
        self.rtt_hist: Deque[float] = deque(maxlen=48)
        self.ack_times: Deque[float] = deque(maxlen=40)
        self.bw_samples: Deque[tuple[float, float]] = deque(maxlen=48)
        self.delivered_marks: Deque[tuple[float, float]] = deque()
        self.cum_delivered = 0.0
        self.loss_burst: Deque[float] = deque(maxlen=20)
        self.last_reconfig_t = -1e9
        self.reprobe_until = 0.0
        self.reprobe_phase_b = 0.0
        self.mode = "startup"
        self.consec_loss = 0
        self.reconfigs_detected = 0
        # Adaptive detection state
        self.rtt_ewma = 0.0
        self.rtt_var_ewma = 0.0
        self.rate_ewma = 0.0
        self.detect_cooldown = 0.42
        self.score_threshold = 1.65
        # Prior epoch scale (soft knowledge, not trusted samples)
        self.prior_bdp = 20 * MSS
        self.prior_bw = 0.0
        self.hint_capacity_bps = 0.0
        self.hint_epoch = -1
        self.stable_acks = 0
        self._last_pace_t = 0.0
        # ASCENT freeze window
        self.freeze_until = -1.0
        self.pending_reprobe_after_freeze = False
        self.high_delay_streak = 0
        self._start_t = -1.0
        self._minrtt_age_t = 0.0
        # OrbCC hybrid state
        self.last_path_id: Optional[int] = None
        self._orb_mobility_until = -1.0
        self._last_signal_confidence = 0.0
        self.orb_path_changes = 0
        self.ascent_d_applied = 0
        # Assist primary: ASCENT/hint reconfigs suppress Orb pathID REPROBE
        self._last_assist_reconfig_t = -1e9
        self._assist_suppress_s = 2.0
        self.orb_reprobe_suppressed = 0
        self._last_path_id_change_t = -1e9
        # DTCE (PR C): cross-epoch cruise envelope
        self.cruise_bw_ring: Deque[float] = deque(maxlen=8)
        self.cruise_rtt_ring: Deque[float] = deque(maxlen=8)
        self._cruise_stable_acks = 0
        self.posthop_track = "idle"  # idle | race | hi | lo
        self._envelope_hi = 0.0
        self._envelope_lo = 0.0
        self._race_until = -1.0

    @staticmethod
    def _median(xs: list[float]) -> float:
        if not xs:
            return 0.0
        s = sorted(xs)
        return s[len(s) // 2]

    @staticmethod
    def _mad(xs: list[float], med: float) -> float:
        if not xs:
            return 0.0
        devs = sorted(abs(x - med) for x in xs)
        return devs[len(devs) // 2]

    @staticmethod
    def _pct(xs: list[float], q: float) -> float:
        if not xs:
            return 0.0
        s = sorted(xs)
        if len(s) == 1:
            return s[0]
        idx = max(0, min(len(s) - 1, int(q * (len(s) - 1))))
        return s[idx]

    def _capture_cruise_sample(self, t: float, rtt_s: float, delay_ratio: float) -> None:
        """Record stable cruise samples into envelope rings (never clear rings on REPROBE)."""
        age = t - self.last_reconfig_t
        if self.fair_mode or self.bw_est <= 0 or self.min_rtt >= 1e17:
            self._cruise_stable_acks = 0
            return
        if (
            self.mode == "cruise"
            and delay_ratio < 1.35
            and age > 1.2
            and t >= self.reprobe_until
            and t >= self.freeze_until
        ):
            self._cruise_stable_acks += 1
            if self._cruise_stable_acks >= 2:
                self.cruise_bw_ring.append(self.bw_est)
                self.cruise_rtt_ring.append(rtt_s if rtt_s > 0 else self.min_rtt)
        else:
            self._cruise_stable_acks = 0

    def _update_rtt_stats(self, rtt_s: float) -> None:
        if self.rtt_ewma <= 0:
            self.rtt_ewma = rtt_s
            self.rtt_var_ewma = 0.0
            return
        alpha = 0.15
        err = rtt_s - self.rtt_ewma
        self.rtt_ewma += alpha * err
        self.rtt_var_ewma = (1 - alpha) * self.rtt_var_ewma + alpha * abs(err)

    def _delivery_rate_sample(self, t: float) -> float:
        if len(self.delivered_marks) < 2:
            return 0.0
        t0, b0 = self.delivered_marks[0]
        t1, b1 = self.delivered_marks[-1]
        dt = t1 - t0
        if dt <= 1e-4:
            return 0.0
        return (b1 - b0) * 8.0 / dt

    def _detect_reconfig(self, t: float, rtt_s: float) -> tuple[bool, float, str]:
        """Return (hit, score, reason) using multi-signal fusion."""
        self.ack_times.append(t)
        self.rtt_hist.append(rtt_s)
        self._update_rtt_stats(rtt_s)
        if self._start_t < 0:
            self._start_t = t
        if t - self._start_t < 0.45 or len(self.rtt_hist) < 8:
            return False, 0.0, ""

        base = list(self.rtt_hist)[:-1]
        med = self._median(base)
        mad = max(self._mad(base, med), 0.002)
        # Adaptive absolute floor from EWMA noise (LEO jumps are tens of ms)
        abs_floor = max(0.010, min(0.030, 2.5 * self.rtt_var_ewma + 0.008))

        score = 0.0
        reasons: list[str] = []

        # Signal 1: robust RTT MAD z-score + absolute jump
        z = (rtt_s - med) / (1.4826 * mad)
        if z > 3.5 and rtt_s - med > abs_floor:
            score += min(2.6, 0.6 * z)
            reasons.append("rtt_mad")
        elif rtt_s > med * 1.65 and rtt_s - med > abs_floor * 1.3:
            score += 1.25
            reasons.append("rtt_jump")

        # Signal 2: ACK inter-arrival freeze (LeoCC-style response interval)
        if len(self.ack_times) >= 8:
            ias = [
                self.ack_times[i] - self.ack_times[i - 1]
                for i in range(1, len(self.ack_times))
            ]
            ia_med = self._median(ias[:-1]) if len(ias) > 1 else self._median(ias)
            ia_mad = max(self._mad(ias[:-1] if len(ias) > 1 else ias, ia_med), 1e-4)
            ia_z = (ias[-1] - ia_med) / (1.4826 * ia_mad)
            if ia_z > 4.0 and ias[-1] > max(0.04, 2.2 * ia_med):
                score += min(2.1, 0.5 * ia_z)
                reasons.append("ack_ia")

        # Signal 3: delivery-rate collapse vs EWMA (path capacity drop / freeze)
        rate = self._delivery_rate_sample(t)
        if rate > 0 and self.rate_ewma > 1e6:
            if rate < 0.28 * self.rate_ewma:
                score += 1.35
                reasons.append("rate_drop")
            elif rate < 0.45 * self.rate_ewma and z > 2.2:
                score += 0.75
                reasons.append("rate_soft")

        # Signal 4: mobility loss burst without delay inflation
        recent_loss = [x for x in self.loss_burst if t - x < 0.32]
        if len(recent_loss) >= 3 and self.min_rtt < 1e17 and rtt_s < 1.35 * self.min_rtt:
            score += 1.4
            reasons.append("loss_burst")
        elif len(recent_loss) >= 2 and z > 2.5:
            score += 0.65
            reasons.append("loss_rtt")

        # Cooldown: suppress double-fire, but allow strong signals
        if t - self.last_reconfig_t < self.detect_cooldown:
            if score < self.score_threshold + 1.0:
                return False, score, ""

        # Classic absolute RTT jump (strong alone)
        classic_jump = rtt_s > med * 1.55 and rtt_s - med > 0.012
        if classic_jump and "rtt_jump" not in reasons and "rtt_mad" not in reasons:
            score = max(score, self.score_threshold)
            reasons.append("rtt_classic")

        # Dual-signal gate: prefer multi-evidence unless classic jump / strong MAD
        strong_solo = "rtt_classic" in reasons or "rtt_mad" in reasons or "loss_burst" in reasons
        multi = len(set(reasons)) >= 2
        hit = (score >= self.score_threshold and (strong_solo or multi)) or (
            classic_jump and rtt_s - med > 0.018
        )
        reason = "+".join(reasons) if reasons else "fused"
        return hit, score, reason

    def _should_suppress_orb_reprobe(self, t: float) -> bool:
        """PR A: block Orb pathID REPROBE when assist/freeze/REPROBE owns the hop."""
        if (t - self._last_assist_reconfig_t) <= self._assist_suppress_s:
            return True
        if t < self.reprobe_until:
            return True
        if t < self.freeze_until or self.pending_reprobe_after_freeze:
            return True
        if (t - self.last_reconfig_t) < self.detect_cooldown:
            return True
        return False

    def _enter_reprobe(
        self,
        t: float,
        reason: str,
        *,
        predicted_cap: float = 0.0,
        predicted_rtt: float = 0.0,
        confidence: float = 0.6,
    ) -> None:
        # Belt-and-suspenders: never apply Orb cut while suppress active
        if reason.startswith("orb") and self._should_suppress_orb_reprobe(t):
            self.orb_reprobe_suppressed += 1
            return
        # Preserve prior scale as soft ceiling knowledge
        if self.min_rtt < 1e17 and self.bw_est > 0:
            self.prior_bdp = max(8 * MSS, self.bw_est * self.min_rtt / 8.0)
            self.prior_bw = self.bw_est
        elif self.prior_bw <= 0 and predicted_cap > 0:
            self.prior_bw = predicted_cap

        self.last_reconfig_t = t
        self.reconfigs_detected += 1
        conf = max(0.0, min(1.0, float(confidence)))
        self._last_signal_confidence = conf
        if reason.startswith("hint"):
            self._last_assist_reconfig_t = t
        rtt_ref = self.min_rtt if self.min_rtt < 1e17 else (
            predicted_rtt if predicted_rtt > 0 else 0.04
        )
        # Two-phase REPROBE: higher confidence -> slightly shorter explore
        phase_a = max(0.05, (1.05 if conf >= 0.9 else 1.15) * rtt_ref)
        phase_b = max(0.09, (1.65 if conf >= 0.9 else 1.85) * rtt_ref)
        self.reprobe_phase_b = t + phase_a
        self.reprobe_until = t + phase_a + phase_b
        self.stable_acks = 0

        # Invalidate epoch samples (key LEO move - unlike BBR stale min-RTT)
        self.min_rtt = float("inf")
        self.bw_samples.clear()
        self.delivered_marks.clear()
        self.bw_est = 0.0
        self.rtt_hist.clear()
        self.rtt_ewma = 0.0
        self.rtt_var_ewma = 0.0
        # Soft cut (not CUBIC collapse). Base by source; confidence softens slightly
        # (assist conf ~0.9-0.95; endpoint ~0.45-0.85). Matches multi-seed hybrid dual-gate.
        if reason.startswith("orb"):
            cut = 0.64
        elif reason.startswith("hint"):
            cut = 0.62
        else:
            cut = 0.58  # exact v3.1 endpoint cut
        if conf >= 0.9:
            cut = min(0.70, cut + 0.04)
        if self.fair_mode:
            cut *= 0.95
        self.cwnd = max(6 * MSS, self.cwnd * cut)
        # Seed bw from prior without trusting stale min-RTT
        if self.prior_bw > 0:
            self.bw_est = self.prior_bw * 0.75
        if predicted_cap > 0:
            self.hint_capacity_bps = predicted_cap
            self.bw_est = max(self.bw_est, predicted_cap * 0.55)
            if predicted_rtt > 0:
                pred_bdp = predicted_cap * predicted_rtt / 8.0
                self.cwnd = max(self.cwnd, min(pred_bdp * 0.55, self.prior_bdp * 0.95))
        self.ssthresh = self.cwnd
        self.pacing_rate_bps = max(
            self.prior_bw * 0.95 if self.prior_bw > 0 else 0.0,
            self.hint_capacity_bps * 0.75 if self.hint_capacity_bps > 0 else 0.0,
            self.cwnd * 8 / max(rtt_ref, 0.02) * 2.2,
        )
        self._pace_credit = max(self._pace_credit, self.cwnd * 1.2)
        self.loss_burst.clear()
        self._minrtt_age_t = t
        self.mode = f"reprobe:{reason}"
        # DTCE: set post-hop envelope race (do not clear cruise rings)
        self._cruise_stable_acks = 0
        if not self.fair_mode:
            bws = list(self.cruise_bw_ring)
            if len(bws) >= 2:
                lo = self._pct(bws, 0.25)
                hi = self._pct(bws, 0.75)
            elif self.prior_bw > 0:
                lo = self.prior_bw * 0.70
                hi = self.prior_bw * 1.05
            else:
                lo = self.bw_est if self.bw_est > 0 else 0.0
                hi = max(lo * 1.15, lo)
            if predicted_cap > 0:
                hi = max(hi, predicted_cap * 0.95)
            if lo > 0 and hi >= lo:
                self._envelope_lo = lo
                self._envelope_hi = hi
                self.posthop_track = "race"
                self._race_until = t + 1.5
                # Seed bw from lo, pace toward hi
                self.bw_est = max(self.bw_est, lo * 0.85)
                self.pacing_rate_bps = max(self.pacing_rate_bps, hi * 0.90)
            else:
                self.posthop_track = "idle"
                self._race_until = -1.0
        else:
            self.posthop_track = "idle"
            self._race_until = -1.0

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
        # Endpoint-only default: ignore all hints unless enabled
        if not self.use_path_hints:
            return
        if next_capacity_bps and next_capacity_bps > 0:
            self.hint_capacity_bps = float(next_capacity_bps)
        if capacity_bps and capacity_bps > 0:
            self.hint_capacity_bps = float(capacity_bps)

        # ASCENT freeze: hold growth, pre-position to next_capacity, then REPROBE
        if freeze_active or (freeze_remaining_s is not None and freeze_remaining_s > 0):
            rem = float(freeze_remaining_s or 0.0)
            self.freeze_until = max(self.freeze_until, t + rem)
            self.pending_reprobe_after_freeze = True
            self.mode = "ascent_freeze"
            nxt = float(next_capacity_bps or self.hint_capacity_bps or 0.0)
            if nxt > 0:
                self.hint_capacity_bps = nxt
                if self.bw_est > nxt * 1.25:
                    self.bw_est = 0.85 * self.bw_est + 0.15 * nxt
                self.pacing_rate_bps = max(self.pacing_rate_bps * 0.92, nxt * 0.55)
            self.cwnd = min(self.cwnd, max(self.cwnd * 0.97, 8 * MSS))
            return

        if epoch is not None and epoch == self.hint_epoch and not reconfigured:
            return
        if reconfigured:
            if epoch is not None:
                self.hint_epoch = epoch
            self.ascent_d_applied += 1
            self._last_assist_reconfig_t = t
            self._enter_reprobe(
                t,
                "hint",
                predicted_cap=float(
                    capacity_bps or next_capacity_bps or self.hint_capacity_bps or 0.0
                ),
                predicted_rtt=float(rtt_s or 0.0),
                confidence=0.9,
            )
        elif capacity_bps and capacity_bps > 0 and t - self.last_reconfig_t < 2.0:
            self.hint_capacity_bps = capacity_bps
            if self.bw_est <= 0:
                self.bw_est = 0.55 * capacity_bps

    def on_orb_signal(self, t: float, sig: "OrbSignal") -> None:
        """PR A hybrid fuse: pathID + mobility; util-MD only in Orb-only mode."""
        if not self.use_orb_signals:
            return
        bdp = sig.bw_bps * max(sig.avg_rtt_s, 1e-3) / 8.0

        if self.last_path_id is not None and sig.path_id != self.last_path_id:
            self.orb_path_changes += 1
            self.last_path_id = sig.path_id
            self._last_path_id_change_t = t
            if self._should_suppress_orb_reprobe(t):
                self.orb_reprobe_suppressed += 1
                if sig.bw_bps > 0 and (t < self.reprobe_until or t < self.freeze_until):
                    if self.bw_est > 0:
                        self.bw_est = 0.92 * self.bw_est + 0.08 * sig.bw_bps
                    else:
                        self.bw_est = sig.bw_bps * 0.55
                    self.hint_capacity_bps = max(self.hint_capacity_bps, sig.bw_bps)
            else:
                self._enter_reprobe(
                    t,
                    "orb:path_id",
                    predicted_cap=sig.bw_bps if sig.bw_bps > 0 else 0.0,
                    predicted_rtt=float(sig.avg_rtt_s or 0.0),
                    confidence=0.95,
                )
        else:
            self.last_path_id = sig.path_id

        # Mobility marks only in Orb-only mode near path events (not hybrid).
        if not self.use_path_hints:
            near = (t - self.last_reconfig_t) < 1.2 or (t - self._last_path_id_change_t) < 1.0
            if near and sig.qlen_bytes < 0.1 * max(bdp, 1.0):
                self._mark_recent_loss_as_mobility(t)

        if t < self.reprobe_until or t < self.freeze_until:
            return

        # Hybrid: never util-MD
        if self.use_path_hints:
            return

        if (
            sig.bottleneck_u >= self.orb_eta * 1.08
            and sig.qlen_bytes > 0.35 * max(bdp, 1.0)
        ):
            factor = max(0.90, self.orb_eta / max(sig.bottleneck_u, 1e-6))
            self.cwnd = max(6 * MSS, self.cwnd * factor)
            self.mode = "orb_util_md"
        elif sig.bw_bps > 0 and self.bw_est > 0 and t - self.last_reconfig_t > 0.5:
            self.bw_est = 0.98 * self.bw_est + 0.02 * sig.bw_bps

    def _mark_recent_loss_as_mobility(self, t: float) -> None:
        """Reinforce mobility taxonomy when in-network queue is near empty."""
        self._orb_mobility_until = max(self._orb_mobility_until, t + 0.4)
        if self.mode not in ("reprobe_explore", "reprobe_fill", "ascent_freeze"):
            if "orb" not in self.mode:
                self.mode = "orb_mobility_hint"

    def on_ecn(self, t: float, ce_count: int = 1) -> None:
        # Production hook: treat CE like mild congestive signal
        if t - self.last_reconfig_t < 0.5:
            return  # ignore ECN noise right after mobility
        factor = max(0.85, 1.0 - 0.05 * min(ce_count, 3))
        self.cwnd = max(4 * MSS, self.cwnd * factor)
        self.ssthresh = min(self.ssthresh, self.cwnd)
        self.mode = "ecn_backoff"

    def can_send(self, t: float) -> int:
        room = max(0.0, self.cwnd - self.bytes_in_flight)
        # Soft pacing: only bind when clearly over-rate (avoid recovery starvation)
        if self.pacing_rate_bps > 0 and t >= self.reprobe_until:
            if self._last_pace_t <= 0:
                self._last_pace_t = t
            dt = max(0.0, t - self._last_pace_t)
            self._last_pace_t = t
            self._pace_credit += self.pacing_rate_bps * dt / 8.0
            cap = max(self.cwnd * 2.5, 24 * MSS)
            self._pace_credit = min(self._pace_credit, cap)
            # Allow up to 1.5x pacing burst vs pure rate
            room = min(room, max(self._pace_credit * 1.5, 4 * MSS))
        return int(room // MSS) * MSS

    def on_sent(self, n: int) -> None:
        super().on_sent(n)
        self._pace_credit = max(0.0, self._pace_credit - n)

    def on_ack(self, t: float, rtt_s: float, bytes_acked: int, lost: int = 0) -> None:
        self.on_delivered(bytes_acked)

        # Exit ASCENT freeze -> scheduled REPROBE
        if self.freeze_until > 0 and t >= self.freeze_until and self.pending_reprobe_after_freeze:
            self.pending_reprobe_after_freeze = False
            self.freeze_until = -1.0
            self._enter_reprobe(
                t,
                "hint:freeze_end",
                predicted_cap=self.hint_capacity_bps,
                predicted_rtt=rtt_s,
                confidence=0.88,
            )

        # During freeze: measure but do not grow aggressively
        if t < self.freeze_until:
            self.mode = "ascent_freeze"
            if rtt_s < self.min_rtt:
                self.min_rtt = rtt_s
            # tiny growth to avoid starvation
            self.cwnd = min(self.cwnd + bytes_acked * 0.15, self.cwnd * 1.02 + MSS)
            return

        hit, score, reason = self._detect_reconfig(t, rtt_s)
        if hit and t - self.last_reconfig_t > self.detect_cooldown * 0.85:
            # Endpoint confidence from fusion score (capped below assist paths)
            ep_conf = min(0.85, 0.45 + 0.12 * max(0.0, score))
            self._enter_reprobe(t, f"ep:{reason}", confidence=ep_conf)

        if rtt_s < self.min_rtt:
            self.min_rtt = rtt_s
            self._minrtt_age_t = t
        elif (
            self.min_rtt < 1e17
            and t - self._minrtt_age_t > 6.0
            and len(self.rtt_hist) >= 12
        ):
            recent_min = min(list(self.rtt_hist)[-12:])
            if recent_min > self.min_rtt * 1.15:
                self.min_rtt = recent_min * 0.95
            self._minrtt_age_t = t

        # Delivery-rate estimate (post-reconfig samples only)
        self.cum_delivered += bytes_acked
        self.delivered_marks.append((t, self.cum_delivered))
        win = max(0.2, 5 * (self.min_rtt if self.min_rtt < 1e17 else 0.04))
        while self.delivered_marks and (
            t - self.delivered_marks[0][0] > win
            or self.delivered_marks[0][0] < self.last_reconfig_t
        ):
            self.delivered_marks.popleft()
        if len(self.delivered_marks) >= 2:
            t0, b0 = self.delivered_marks[0]
            t1, b1 = self.delivered_marks[-1]
            dt = t1 - t0
            if dt > 1e-4:
                sample = (b1 - b0) * 8.0 / dt
                self.bw_samples.append((t, sample))
                if self.rate_ewma <= 0:
                    self.rate_ewma = sample
                else:
                    self.rate_ewma = 0.2 * sample + 0.8 * self.rate_ewma
        while self.bw_samples and (
            self.bw_samples[0][0] < self.last_reconfig_t
            or t - self.bw_samples[0][0] > win * 2
        ):
            self.bw_samples.popleft()
        age = t - self.last_reconfig_t
        delay_ratio_early = (
            rtt_s / self.min_rtt if self.min_rtt < 1e17 and self.min_rtt > 0 else 1.0
        )
        if self.bw_samples:
            vals = sorted(b for _, b in self.bw_samples)
            pct = 0.70 if self.fair_mode else 0.82
            pct_val = vals[int(pct * (len(vals) - 1))]
            max_val = vals[-1]
            if (
                not self.fair_mode
                and age < 1.0
                and len(vals) >= 3
                and delay_ratio_early < 1.50
            ):
                self.bw_est = max(pct_val, 0.55 * pct_val + 0.45 * max_val)
            else:
                self.bw_est = pct_val
            if self.prior_bw > 0 and age < 2.0 and not self.fair_mode:
                floor_frac = max(0.42, 0.72 - 0.14 * age)
                if delay_ratio_early < 1.6:
                    self.bw_est = max(self.bw_est, self.prior_bw * floor_frac)
            elif self.prior_bw > 0 and age < 1.5:
                self.bw_est = max(self.bw_est, self.prior_bw * 0.55)
            if self.hint_capacity_bps > 0:
                self.bw_est = 0.72 * self.bw_est + 0.28 * self.hint_capacity_bps

        if self.bw_est > 0:
            self.pacing_rate_bps = self.bw_est * (
                1.35 if t < self.reprobe_until else (1.0 if self.fair_mode else 1.08)
            )
        elif self.prior_bw > 0:
            self.pacing_rate_bps = self.prior_bw * 0.65

        # ---- REPROBE two-phase ----
        if t < self.reprobe_until:
            in_b = t >= self.reprobe_phase_b
            self.mode = "reprobe_fill" if in_b else "reprobe_explore"
            growth = (1.55 if in_b else 1.25) * (0.9 if self.fair_mode else 1.0)
            self.cwnd += bytes_acked * growth
            ceiling = max(96 * MSS, self.prior_bdp * 1.65)
            if self.bw_est > 0 and self.min_rtt < 1e17:
                ceiling = max(ceiling, 2.0 * self.bw_est * self.min_rtt / 8.0)
            if self.hint_capacity_bps > 0 and self.min_rtt < 1e17:
                ceiling = max(
                    ceiling, 1.5 * self.hint_capacity_bps * self.min_rtt / 8.0
                )
            self.cwnd = min(self.cwnd, ceiling)
            if (
                in_b
                and self.bw_est > 0
                and self.min_rtt < 1e17
                and self.rtt_var_ewma < 0.32 * max(self.min_rtt, 0.02)
            ):
                self.stable_acks += 1
                if self.stable_acks >= 3:
                    self.reprobe_until = t
                    self.mode = "cruise"
                    self.ssthresh = self.cwnd
            return

        if lost > 0 and self.min_rtt < 1e17 and rtt_s > 1.45 * self.min_rtt:
            self.consec_loss += 1
        else:
            self.consec_loss = 0

        sizing_rtt = self.min_rtt if self.min_rtt < 1e17 else max(rtt_s, 0.02)
        if len(self.rtt_hist) >= 8 and self.min_rtt < 1e17:
            recent_med = self._median(list(self.rtt_hist)[-8:])
            if recent_med > 1.7 * self.min_rtt:
                sizing_rtt = 0.40 * self.min_rtt + 0.60 * recent_med
            else:
                sizing_rtt = 0.75 * self.min_rtt + 0.25 * recent_med
        bdp = 10 * MSS
        if sizing_rtt > 0 and self.bw_est > 0:
            bdp = self.bw_est * sizing_rtt / 8.0

        path_floor = sizing_rtt
        if len(self.rtt_hist) >= 12:
            path_floor = max(min(list(self.rtt_hist)[-12:]), sizing_rtt * 0.85)
        delay_ratio = rtt_s / max(path_floor, 1e-4)
        if delay_ratio > 1.5:
            self.high_delay_streak += 1
        else:
            self.high_delay_streak = max(0, self.high_delay_streak - 1)

        # DTCE post-hop race (~1.5s): continuity reclaims hi; redraw-down abandons
        if (
            not self.fair_mode
            and self.posthop_track in ("race", "hi", "lo")
            and t < self._race_until
            and self._envelope_hi > 0
        ):
            measured = self.bw_est if self.bw_est > 0 else 0.0
            if delay_ratio < 1.30 and measured >= 0.80 * self._envelope_hi:
                self.posthop_track = "hi"
                self.bw_est = max(self.bw_est, 0.55 * self.bw_est + 0.45 * self._envelope_hi)
                target_bdp = self._envelope_hi * sizing_rtt / 8.0 if sizing_rtt > 0 else self.cwnd
                self.cwnd = max(self.cwnd, min(self.cwnd * 1.08 + MSS, target_bdp * 1.05))
                self.pacing_rate_bps = max(self.pacing_rate_bps, self._envelope_hi * 1.05)
                self.mode = "dtce_hi"
            elif delay_ratio > 1.55:
                self.posthop_track = "lo"
                self.bw_est = min(self.bw_est if self.bw_est > 0 else self._envelope_lo, self._envelope_lo * 1.05)
                self.mode = "dtce_lo"
            else:
                self.posthop_track = "race"
                floor_bdp = self._envelope_lo * sizing_rtt / 8.0 if sizing_rtt > 0 else self.cwnd
                self.cwnd = max(self.cwnd, min(self.cwnd + MSS * 0.5, max(floor_bdp, 8 * MSS)))
                self.pacing_rate_bps = max(self.pacing_rate_bps, self._envelope_hi * 0.85)
                self.mode = "dtce_race"
        elif t >= self._race_until and self.posthop_track != "idle":
            self.posthop_track = "idle"

        self._capture_cruise_sample(t, rtt_s, delay_ratio)

        if self.cwnd < self.ssthresh or self.mode in (
            "startup",
            "reprobe_explore",
            "reprobe_fill",
            "mobility_loss",
            "ascent_freeze",
        ):
            self.mode = "startup"
            self.cwnd += bytes_acked * (1.15 if self.fair_mode else 1.35)
            if self.cwnd >= bdp * 0.88 and self.bw_est > 0:
                self.mode = "cruise"
                self.ssthresh = self.cwnd
        else:
            # fair_mode: AIMD-ish around 1.0x BDP; else mild probe 1.18x
            target = (1.02 if self.fair_mode else 1.18) * bdp
            if self.fair_mode and (delay_ratio > 1.45 or self.high_delay_streak >= 3):
                self.cwnd = max(4 * MSS, self.cwnd * 0.92)
                self.mode = "fair_yield"
            elif delay_ratio > 2.0:
                self.cwnd = max(4 * MSS, self.cwnd - MSS * 0.2)
                self.mode = "delay_yield"
            elif self.cwnd < target:
                step = MSS * (0.45 if self.fair_mode else 0.95)
                self.cwnd += step
                self.mode = "cruise"
            elif self.cwnd > target * 1.2:
                self.cwnd -= MSS * (0.2 if self.fair_mode else 0.12)
                self.mode = "cruise"
            else:
                self.mode = "cruise"
            self.cwnd = max(4 * MSS, self.cwnd)

    def on_loss(self, t: float, bytes_lost: int, congestive: bool) -> None:
        self.on_delivered(bytes_lost)
        self.loss_burst.append(t)
        # OrbCC / empty-queue hint: treat as mobility even if labeled congestive
        if t < self._orb_mobility_until and congestive:
            congestive = False
        # Non-congestive (mobility) loss: do not collapse cwnd
        if not congestive:
            if t - self.last_reconfig_t < 1.4:
                self.mode = "mobility_loss"
                return
            if self.min_rtt < 1e17 and len(self.rtt_hist) >= 2:
                recent_rtt = self.rtt_hist[-1]
                if recent_rtt < 1.45 * self.min_rtt:
                    self.mode = "mobility_loss"
                    if t - self.last_reconfig_t > self.detect_cooldown and len(
                        [x for x in self.loss_burst if t - x < 0.28]
                    ) >= 2:
                        self._enter_reprobe(t, "ep:loss_burst", confidence=0.7)
                    return
        # True congestion: slightly milder than CUBIC for multi-flow friendliness
        self.ssthresh = max(4 * MSS, self.cwnd * 0.72)
        self.cwnd = self.ssthresh
        self.pacing_rate_bps = max(
            self.pacing_rate_bps * 0.7,
            self.cwnd * 8 / max(self.min_rtt if self.min_rtt < 1e17 else 0.05, 0.02),
        )
        self.mode = "congestive_recovery"
