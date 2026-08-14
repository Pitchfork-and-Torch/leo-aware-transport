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
        # Decreasing-sample deque: bw_est == max(sample) over bw_window in O(1).
        # Identity vs scanning max(); required at LeoCC ~400 Mbps (16k marks / 0.5s).
        self.bw_max_q: Deque[tuple[float, float]] = deque()
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
                while self.bw_max_q and self.bw_max_q[-1][1] <= sample:
                    self.bw_max_q.pop()
                self.bw_max_q.append((t, sample))
        while self.bw_window and t - self.bw_window[0][0] > win:
            t0, _ = self.bw_window.popleft()
            if self.bw_max_q and self.bw_max_q[0][0] == t0:
                self.bw_max_q.popleft()
        if self.bw_max_q:
            # max filter (BBR-style); same value as max(b for _, b in bw_window)
            self.bw_est = self.bw_max_q[0][1]

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
    LeoAware v3.10 Halo - EpochMemory + HO-PLL + Soft Surplus Echo (OrbitStack).

    Product lock era is starlink_v1 (absolute gp≥75 AND p95≤138.8).
    ope_v36 remains the research relative-BBR path. Do not mix eras.

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

    v3.3-A' / v3.4-p95 reclaim (endpoint multi-seed p95 under BBR):
      - Cruise delay_yield earlier (ratio ~1.45+) + BDP overshoot cap when delayed
      - Soften post-hop max-filter / prior floor when delay elevated
      - REPROBE fill ceiling lower + earlier stable/delay exit (no full DTCE)
      - Sizing RTT leans on recent median when delay_ratio risk is high
      - Hybrid fuse rails unchanged; suite default still endpoint-only

    v3.5 Tide:
      - Time-bounded post-hop reclaim (TBPR) after REPROBE→cruise.

    v3.6 Keel (pairs with sim OPE + soft-QIR):
      - Cross-Epoch Delay Anchor ("keel"): preserve pre-hop min_rtt across REPROBE
        invalidation so TBPR/yield still see inflation when live RTT ≫ prior base.
      - Two-Phase Commit reclaim: commit_cwnd at reclaim arm; if keel_ratio or
        delay_ratio spikes, abort TBPR and roll cwnd back to the commit point.
      - REPROBE fill ceiling uses min(min_rtt, keel·1.2) when inflated vs keel.
      - Selective Epoch Reset (SER): pure ep:loss_burst keeps min_rtt, mild cut,
        short fill — full invalidate stays for rtt_mad/ack_ia.
      - Clean-cruise ~1.38× BDP on OPE-fair paths.

    v3.7 OCE (novel):
      - Orbit Capacity Echo: after SER/SER-lite, for ~3 RTT if delay stays clean,
        chase delivery-rate into bw_est and push toward ~1.42× BDP; abort to the
        OCE commit cwnd if delay_ratio > 1.30 (transactional echo).
      - SER-lite: ack_ia+loss_burst without rtt_mad/loss_rtt keeps min_rtt (ACK
        freeze ≠ path RTT jump); cut 0.80, short fill — full invalidate stays for
        true RTT-jump reasons.
      - Widens OPE-fair dual-gate margin vs BBR without re-gating loss_burst detect.

    v3.9 Crest (starlink_v1 product-lock era):
      - Crest Abort (CA-hard): abort TBPR/OCE reclaim on RTT crest
        (rtt > k×recent_median, k≈1.35) with 2-sample hysteresis or
        crest+rising delay_ratio. Cruise/reclaim only — never during REPROBE
        explore/fill. Never gates ep:loss_burst.
      - Dual-Ledger Cruise (DLC): cwnd_safe vs cwnd_tide; fly tide only if
        delay is clean AND no crest. Stretch cap ≤1.42× BDP. Not DTCE (no
        cross-epoch fill race).
      - Local Surplus Guard (LSG): cruise stretch only if delivery EWMA
        ≥ ~0.85×prior_bw and local RTT is healthy. No seed-id branching.
      - Optional freeze-only anticipator: ACK-IA growth freeze only; never
        suppresses detection.

    v3.10 Halo / Orbit Pulse — REJECTED on starlink_v1 (failed to clear BBR;
      often regressed Crest). Flags default OFF; Crest remains product CCA.

    v3.10 Capacity Fade/Rise Echo (CFR/CRE) — research levers for mid-epoch
      capacity flicker (starlink_v2 / real CSV):
      - CFR: delivery collapse without RTT inflation → soft-cut cwnd/bw_est
        (no min_rtt invalidate).
      - CRE: delivery surge vs bw_est with clean delay → lift bw_est toward
        live rate (BBR max-filter gap without abandoning hop invalidation).
      - Default ON; near no-op on sticky starlink_v1.

    v3.10-QSP (this cook): Queue-Sojourn Pacing. Invert visible soft-QIR
      excess (α stays frozen 0.20) and discount pace_gain only. Never raises
      cruise BDP. Default OFF until 5-seed Pareto vs Crest.

    v3.10 SkyPulse: PATHHINT ingest via existing ASCENT-D path
      (`hint_freeze_only`). Growth-freeze only — never hint-REPROBE, never
      gate ep:loss_burst. Public suite stays `use_path_hints=False`.

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
        use_ca: bool = True,
        use_dlc: bool = True,
        use_lsg: bool = True,
        use_anticipator: bool = True,
        use_halo: bool = False,
        use_orbit_pulse: bool = False,
        use_cfr: bool = False,
        use_qsp: bool = False,
        hint_freeze_only: bool = False,
        use_spike_hold: bool = False,
        **kw,
    ):
        super().__init__(**kw)
        self.use_path_hints = use_path_hints
        self.fair_mode = fair_mode
        self.use_orb_signals = use_orb_signals
        self.orb_eta = float(orb_eta)
        self.use_ca = bool(use_ca)
        self.use_dlc = bool(use_dlc)
        self.use_lsg = bool(use_lsg)
        self.use_anticipator = bool(use_anticipator)
        # v3.10 Halo/Pulse/CFR/CRE rejected for product (failed to clear BBR on
        # starlink_v1; CFR/CRE near no-op on v2 flicker). Defaults = Crest.
        self.use_halo = bool(use_halo)
        self.use_orbit_pulse = bool(use_orbit_pulse)
        self.use_cfr = bool(use_cfr)
        # v3.10-QSP: queue-sojourn pacing (pace-only; never raises cruise BDP).
        # Default OFF until a 5-seed Pareto vs Crest ACCEPT.
        self.use_qsp = bool(use_qsp)
        # SkyPulse: PATHHINT growth-freeze only. Never hint-REPROBE, never
        # gate ep:loss_burst. Public suite keeps use_path_hints=False.
        self.hint_freeze_only = bool(hint_freeze_only)
        # v3.11-SH: RTT jump + delivery still ≥0.90×bw → skip full REPROBE.
        # Held-pipe fill: while no real REPROBE has fired, grow like BBR
        # startup (1.92×) and soft-max-filter bw. WetLinks capacity is held
        # flat; Crest's 1.28× / p82 is the leftover ~7 Mbps 25s tax.
        # Never gates ep:loss_burst. Default OFF (product Crest unchanged).
        self.use_spike_hold = bool(use_spike_hold)
        self._spike_hold_until = -1.0
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
        # v3.5 Tide / v3.6 Keel: time-bounded post-hop reclaim + 2PC
        self._reclaim_until = -1.0
        self._keel_rtt = 0.0
        self._commit_cwnd = 0.0
        self.keel_rollbacks = 0
        # v3.7 OCE: transactional post-SER capacity echo
        self._oce_until = -1.0
        self._oce_commit = 0.0
        self.oce_echos = 0
        self.ser_lite_count = 0
        # v3.9 Crest: CA-hard / DLC / LSG / freeze-only anticipator
        self._crest_streak = 0
        self._prev_delay_ratio = 1.0
        self._ca_hold_until = -1.0
        self._anticipator_until = -1.0
        self.ca_aborts = 0
        self.dlc_tide_flights = 0
        self.lsg_clamps = 0
        self.anticipator_holds = 0
        # v3.10 Halo: EpochMemory (soft) + Orbit Pulse
        self._epoch_bw_mem: Deque[float] = deque(maxlen=4)
        self._pll_until = -1.0  # retained gate for LSG; not aggressive reclaim
        self._halo_seed_bw = 0.0
        self.halo_seeds = 0
        self.pll_windows = 0
        self._pulse_cycle_t = 0.0
        self._pulse_until = -1.0
        self.orbit_pulses = 0
        self._cfr_cooldown_until = -1.0
        self.cfr_cuts = 0
        self.spike_holds = 0
        self.cre_lifts = 0
        self._qsp_excess = 0.0
        self.qsp_discounts = 0
        self.skypulse_freezes = 0

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

    def _crest_hit(self, t: float, rtt_s: float, delay_ratio: float) -> bool:
        """CA-hard crest: rtt > k×recent_median (k≈1.35), cruise/reclaim only.

        Hysteresis: 2 consecutive crest samples, or crest + rising delay_ratio.
        Never fires during REPROBE explore/fill.
        """
        if not self.use_ca or self.fair_mode:
            self._crest_streak = 0
            return False
        if t < self.reprobe_until:
            self._crest_streak = 0
            return False
        if len(self.rtt_hist) < 8:
            return False
        hist = list(self.rtt_hist)
        med = self._median(hist[:-1] if len(hist) > 1 else hist)
        if med <= 1e-6:
            return False
        k = 1.35  # mid of [1.30, 1.45]
        crest = rtt_s > k * med
        rising = delay_ratio > self._prev_delay_ratio + 0.02
        if crest:
            self._crest_streak += 1
        else:
            self._crest_streak = 0
        return self._crest_streak >= 2 or (crest and rising)

    def _epoch_mem_p50(self) -> float:
        if not self._epoch_bw_mem:
            return 0.0
        return self._median(list(self._epoch_bw_mem))

    def _delivery_stable(self, t: float) -> bool:
        """True when live delivery is still ~the estimated pipe (not a cap hop)."""
        rate = self.rate_ewma if self.rate_ewma > 1e6 else self._delivery_rate_sample(t)
        ref = self.bw_est if self.bw_est > 1e6 else self.prior_bw
        if rate < 1e6 or ref < 1e6:
            return False
        return rate >= 0.90 * ref

    def _pipe_hold_active(self) -> bool:
        """Held-capacity assist: SH on and no real REPROBE yet.

        WetLinks windows hold UDP-mean capacity flat. A skipped RTT-spike
        does not increment reconfigs_detected, so this stays armed. A real
        ep:loss_burst SER turns it off. Product Crest never enters (flag off).
        """
        return (
            self.use_spike_hold
            and not self.fair_mode
            and self.reconfigs_detected == 0
        )

    def _pipe_hold_fill(self, t: float) -> bool:
        """First 1.5s of a held pipe: BBR is not pace-bound in this sim."""
        if not self._pipe_hold_active():
            return False
        if self._start_t < 0:
            return True
        return (t - self._start_t) < 1.50

    def _halo_ref_bw(self) -> float:
        """Soft capacity reference: max(prior, epoch-memory p50)."""
        mem = self._epoch_mem_p50()
        prior = self.prior_bw if self.prior_bw > 0 else 0.0
        if mem > 0 and prior > 0:
            return max(prior, mem)
        return mem if mem > 0 else prior

    def _remember_epoch_bw(self, bw: float) -> None:
        if not self.use_halo or self.fair_mode or bw <= 1e6:
            return
        self._epoch_bw_mem.append(float(bw))

    def _lsg_surplus_ok(self, t: float, delay_ratio: float) -> bool:
        """Stretch only if delivery recovered vs prior_bw and RTT is healthy.

        Does not veto an armed OCE/TBPR window (those have CA + delay abort).
        No seed-id branching. Halo softens the bar slightly when EpochMemory
        says the orbit usually carries more than the last prior.
        """
        if not self.use_lsg or self.fair_mode:
            return True
        if t < self._oce_until or t < self._reclaim_until or t < self._pulse_until:
            return True
        if delay_ratio >= 1.18 or self.high_delay_streak > 0:
            return False
        rate = self.rate_ewma if self.rate_ewma > 0 else self._delivery_rate_sample(t)
        ref = self._halo_ref_bw() if self.use_halo else self.prior_bw
        if ref > 1e6 and rate > 0:
            # Slightly softer when memory ≫ last prior (orbit surplus likely).
            bar = 0.85
            if (
                self.use_halo
                and self.prior_bw > 1e6
                and self._epoch_mem_p50() > 1.12 * self.prior_bw
            ):
                bar = 0.82
            return rate >= bar * ref
        return delay_ratio < 1.12

    def _apply_crest_abort(self, t: float, bdp: float) -> None:
        """Abort TBPR/OCE reclaim and drop to the safe ledger."""
        safe = max(4 * MSS, 1.08 * bdp if bdp > 0 else self.cwnd)
        if self._commit_cwnd > 0:
            safe = min(safe, max(4 * MSS, self._commit_cwnd))
        if self.cwnd > safe * 1.02:
            self.cwnd = safe
            self.ca_aborts += 1
            self.mode = "ca_abort"
        self._reclaim_until = min(self._reclaim_until, t)
        self._oce_until = min(self._oce_until, t)
        self._pll_until = min(self._pll_until, t)
        self._pulse_until = min(self._pulse_until, t)
        rtt_ref = self.min_rtt if self.min_rtt < 1e17 else 0.04
        self._ca_hold_until = t + max(0.04, 0.5 * rtt_ref)

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

        # v3.6/v3.7 Selective Epoch Reset family: RTT-stable mobility keeps min_rtt.
        # - pure ep:loss_burst → SER (cut 0.85)
        # - ack_ia+loss_burst without rtt_mad/loss_rtt → SER-lite (cut 0.80)
        # Full invalidate remains for true RTT-jump reasons.
        ser_lite = (
            not self.fair_mode
            and self.min_rtt < 1e17
            and "loss_burst" in reason
            and "rtt_mad" not in reason
            and "loss_rtt" not in reason
            and reason != "ep:loss_burst"
        )
        if (reason == "ep:loss_burst" and not self.fair_mode) or ser_lite:
            if self.min_rtt < 1e17 and self.bw_est > 0:
                self.prior_bdp = max(8 * MSS, self.bw_est * self.min_rtt / 8.0)
                self.prior_bw = self.bw_est
                self._remember_epoch_bw(self.bw_est)
            if self.min_rtt < 1e17:
                if self._keel_rtt <= 0:
                    self._keel_rtt = self.min_rtt
                elif self.min_rtt <= 1.15 * self._keel_rtt:
                    self._keel_rtt = 0.75 * self._keel_rtt + 0.25 * self.min_rtt
            self.last_reconfig_t = t
            self.reconfigs_detected += 1
            self._last_signal_confidence = max(0.0, min(1.0, float(confidence)))
            cut = 0.80 if ser_lite else 0.85
            self.cwnd = max(6 * MSS, self.cwnd * cut)
            self.ssthresh = self.cwnd
            self.bw_samples.clear()
            self.delivered_marks.clear()
            if self.prior_bw > 0:
                self.bw_est = self.prior_bw * 0.90
            rtt_ref = self.min_rtt if self.min_rtt < 1e17 else 0.04
            self.pacing_rate_bps = max(
                self.prior_bw * 0.95 if self.prior_bw > 0 else 0.0,
                self.cwnd * 8 / max(rtt_ref, 0.02) * 1.8,
            )
            self._pace_credit = max(self._pace_credit, self.cwnd * 1.1)
            self.loss_burst.clear()
            self.reprobe_phase_b = t + (0.05 if ser_lite else 0.04)
            self.reprobe_until = t + (0.12 if ser_lite else 0.10)
            self.stable_acks = 0
            self._reclaim_until = t + max(0.12, 2.2 * rtt_ref)
            self._commit_cwnd = self.cwnd
            # v3.7 OCE arm: transactional capacity chase after SER family
            self._oce_until = t + max(0.18, 3.0 * rtt_ref)
            self._oce_commit = self.cwnd
            if ser_lite:
                self.ser_lite_count += 1
                self.mode = f"ser_lite:{reason}"
            else:
                self.mode = "ser:loss_burst"
            return

        # Preserve prior scale as soft ceiling knowledge
        if self.min_rtt < 1e17 and self.bw_est > 0:
            self.prior_bdp = max(8 * MSS, self.bw_est * self.min_rtt / 8.0)
            self.prior_bw = self.bw_est
            self._remember_epoch_bw(self.bw_est)
        elif self.prior_bw <= 0 and predicted_cap > 0:
            self.prior_bw = predicted_cap

        # v3.6 Keel: cross-epoch delay anchor (refuse poison seep upward)
        if self.min_rtt < 1e17:
            if self._keel_rtt <= 0:
                self._keel_rtt = self.min_rtt
            elif self.min_rtt <= 1.15 * self._keel_rtt:
                self._keel_rtt = 0.75 * self._keel_rtt + 0.25 * self.min_rtt
            # else: keep keel; JUMP adoption happens later from stable cruise min

        self.last_reconfig_t = t
        self.reconfigs_detected += 1
        conf = max(0.0, min(1.0, float(confidence)))
        self._last_signal_confidence = conf
        if reason.startswith("hint"):
            self._last_assist_reconfig_t = t
        self._commit_cwnd = 0.0
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
            cut = 0.58  # rtt_mad / ack_ia endpoint cut
        if conf >= 0.9:
            cut = min(0.70, cut + 0.04)
        if self.fair_mode:
            cut *= 0.95
        self.cwnd = max(6 * MSS, self.cwnd * cut)
        # Seed bw from prior / Halo EpochMemory without trusting stale min-RTT
        seed_bw = self.prior_bw
        if self.use_halo and not self.fair_mode:
            halo_ref = self._halo_ref_bw()
            if halo_ref > seed_bw * 1.05:
                # Conservative blend — v1 0.55/0.45 overshot and lost vs Crest.
                seed_bw = 0.70 * seed_bw + 0.30 * halo_ref if seed_bw > 0 else halo_ref
                self.halo_seeds += 1
            self._halo_seed_bw = seed_bw
        if seed_bw > 0:
            self.bw_est = seed_bw * 0.75
        if predicted_cap > 0:
            self.hint_capacity_bps = predicted_cap
            self.bw_est = max(self.bw_est, predicted_cap * 0.55)
            if predicted_rtt > 0:
                pred_bdp = predicted_cap * predicted_rtt / 8.0
                self.cwnd = max(self.cwnd, min(pred_bdp * 0.55, self.prior_bdp * 0.95))
        self.ssthresh = self.cwnd
        pace_ref = seed_bw if seed_bw > 0 else self.prior_bw
        self.pacing_rate_bps = max(
            pace_ref * 0.95 if pace_ref > 0 else 0.0,
            self.hint_capacity_bps * 0.75 if self.hint_capacity_bps > 0 else 0.0,
            self.cwnd * 8 / max(rtt_ref, 0.02) * 2.2,
        )
        self._pace_credit = max(self._pace_credit, self.cwnd * 1.2)
        self.loss_burst.clear()
        self._minrtt_age_t = t
        self._reclaim_until = -1.0
        self._pll_until = -1.0
        self.mode = f"reprobe:{reason}"

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

        # ASCENT / SkyPulse freeze
        if freeze_active or (freeze_remaining_s is not None and freeze_remaining_s > 0):
            rem = float(freeze_remaining_s or 0.0)
            self.freeze_until = max(self.freeze_until, t + rem)
            if self.hint_freeze_only:
                # Growth-freeze only: hold send growth. Endpoint detect owns the
                # hop — never schedule hint REPROBE, never gate ep:loss_burst.
                self.pending_reprobe_after_freeze = False
                self.skypulse_freezes += 1
                self.mode = "skypulse_freeze"
                return
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

        if self.hint_freeze_only:
            # Ingested reconfig/capacity is fail-closed skip for cut/REPROBE.
            if reconfigured:
                self.ascent_d_applied += 1
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

    def _qsp_pace_gain(self, t: float, delay_ratio_early: float, rtt_s: float) -> float:
        """Map visible soft-QIR excess to a pace discount. Does not touch BDP.

        ACK RTT already includes frozen QIR: path + min(25ms, 0.20×sojourn).
        Invert the visible excess (not α — α stays 0.20) and drain standing
        queue by pacing, never by raising cruise BDP.
        """
        base = 1.35 if t < self.reprobe_until else (
            1.0 if self.fair_mode else (1.04 if delay_ratio_early > 1.45 else 1.08)
        )
        if not self.use_qsp or self.fair_mode or t < self.reprobe_until:
            return base
        floor = self.min_rtt if self.min_rtt < 1e17 else 0.0
        excess = max(0.0, rtt_s - floor) if floor > 0 else 0.0
        self._qsp_excess = excess
        # Full-pipe QIR on this harness is ~6ms (terr). Only discount extra.
        extra = max(0.0, excess - 0.006)
        if extra <= 0:
            return base
        discount = min(0.12, extra / 0.010 * 0.06)
        if discount > 0.01:
            self.qsp_discounts += 1
        return max(0.96, base - discount)

    def can_send(self, t: float) -> int:
        room = max(0.0, self.cwnd - self.bytes_in_flight)
        # Soft pacing: only bind when clearly over-rate (avoid recovery starvation)
        if (
            self.pacing_rate_bps > 0
            and t >= self.reprobe_until
            and not self._pipe_hold_fill(t)
        ):
            if self._last_pace_t <= 0:
                self._last_pace_t = t
            dt = max(0.0, t - self._last_pace_t)
            self._last_pace_t = t
            self._pace_credit += self.pacing_rate_bps * dt / 8.0
            cap = max(self.cwnd * 2.5, 24 * MSS)
            self._pace_credit = min(self._pace_credit, cap)
            # QSP: tighten burst when standing-queue excess is visible
            burst = 1.5
            if self.use_qsp and not self.fair_mode and self._qsp_excess > 0.008:
                burst = 1.15
            room = min(room, max(self._pace_credit * burst, 4 * MSS))
        return int(room // MSS) * MSS

    def on_sent(self, n: int) -> None:
        super().on_sent(n)
        self._pace_credit = max(0.0, self._pace_credit - n)

    def on_ack(self, t: float, rtt_s: float, bytes_acked: int, lost: int = 0) -> None:
        self.on_delivered(bytes_acked)

        # Exit ASCENT freeze -> scheduled REPROBE (legacy assist, not SkyPulse)
        if (
            self.freeze_until > 0
            and t >= self.freeze_until
            and self.pending_reprobe_after_freeze
            and not self.hint_freeze_only
        ):
            self.pending_reprobe_after_freeze = False
            self.freeze_until = -1.0
            self._enter_reprobe(
                t,
                "hint:freeze_end",
                predicted_cap=self.hint_capacity_bps,
                predicted_rtt=rtt_s,
                confidence=0.88,
            )

        # Legacy assist freeze: hold + skip detect. SkyPulse freeze-only must
        # NOT take this path — ep:loss_burst / endpoint detect stay live.
        if t < self.freeze_until and not self.hint_freeze_only:
            self.mode = "ascent_freeze"
            if rtt_s < self.min_rtt:
                self.min_rtt = rtt_s
            # tiny growth to avoid starvation
            self.cwnd = min(self.cwnd + bytes_acked * 0.15, self.cwnd * 1.02 + MSS)
            return

        hit, score, reason = self._detect_reconfig(t, rtt_s)
        if hit and t - self.last_reconfig_t > self.detect_cooldown * 0.85:
            # Spike-hold: RTT jump with delivery still on-pipe is not a cap hop.
            # Never skip loss_burst. Do not update last_reconfig_t (detect stays live).
            sh_active = (
                self.use_spike_hold
                and not self.fair_mode
                and t < self._spike_hold_until
                and "loss_burst" not in reason
            )
            sh_arm = (
                self.use_spike_hold
                and not self.fair_mode
                and "loss_burst" not in reason
                and self._delivery_stable(t)
            )
            if sh_active or sh_arm:
                if sh_arm and not sh_active:
                    self.spike_holds += 1
                    self._spike_hold_until = t + 0.50
                self.mode = "spike_hold"
            else:
                # Endpoint confidence from fusion score (capped below assist paths)
                ep_conf = min(0.85, 0.45 + 0.12 * max(0.0, score))
                self._enter_reprobe(t, f"ep:{reason}", confidence=ep_conf)
                self._anticipator_until = -1.0  # REPROBE owns the hop; never suppress detect
        elif (
            self.use_anticipator
            and not self.fair_mode
            and "ack_ia" in reason
            and t >= self.reprobe_until
        ):
            # Freeze-only HO anticipator: hold growth, never detect-suppress.
            if t >= self._anticipator_until:
                self.anticipator_holds += 1
            self._anticipator_until = t + 0.12
        elif (
            self.use_cfr
            and not self.fair_mode
            and not hit
            and t >= self.reprobe_until
            and t >= self._cfr_cooldown_until
            and self.rate_ewma > 1e6
        ):
            # Capacity Fade Response: mid-epoch drop without hop RTT jump.
            # Softer than rate_drop REPROBE; does not invalidate min_rtt.
            rate = self._delivery_rate_sample(t)
            delay_ok = self.min_rtt >= 1e17 or rtt_s < 1.25 * self.min_rtt
            if (
                rate > 1e6
                and delay_ok
                and rate < 0.62 * self.rate_ewma
                and (self.bw_est <= 0 or rate < 0.70 * self.bw_est)
            ):
                new_bw = max(rate, 0.55 * self.rate_ewma)
                if self.bw_est > 0:
                    self.bw_est = 0.35 * self.bw_est + 0.65 * new_bw
                else:
                    self.bw_est = new_bw
                self.rate_ewma = 0.5 * self.rate_ewma + 0.5 * rate
                rtt_ref = self.min_rtt if self.min_rtt < 1e17 else max(rtt_s, 0.02)
                safe = max(4 * MSS, self.bw_est * rtt_ref / 8.0 * 1.05)
                if self.cwnd > safe * 1.05:
                    self.cwnd = max(safe, self.cwnd * 0.82)
                    self.cfr_cuts += 1
                    self.mode = "cfr_fade"
                self.pacing_rate_bps = min(
                    self.pacing_rate_bps, max(self.bw_est * 1.05, 1e6)
                )
                self._cfr_cooldown_until = t + max(0.08, 1.5 * rtt_ref)
            elif (
                rate > 1e6
                and delay_ok
                and self.bw_est > 1e6
                and rate > 1.18 * self.bw_est
                and self.min_rtt < 1e17
                and rtt_s < 1.15 * self.min_rtt
            ):
                # Capacity Rise Echo: track upward flicker (BBR max-filter gap).
                prev = self.bw_est
                self.bw_est = 0.45 * self.bw_est + 0.55 * rate
                if self.bw_est > prev * 1.02:
                    self.cre_lifts += 1
                    self.pacing_rate_bps = max(self.pacing_rate_bps, self.bw_est * 1.10)
                    self.mode = "cre_rise"

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
            # v3.4-p95: keep optimistic pacing, but soft max-filter only when
            # delay is still healthy (avoids queue spikes on seeds 7/99).
            if (
                not self.fair_mode
                and age < 0.85
                and len(vals) >= 3
                and delay_ratio_early < 1.28
            ):
                self.bw_est = max(pct_val, 0.70 * pct_val + 0.30 * max_val)
            elif (
                self._pipe_hold_active()
                and len(vals) >= 3
                and delay_ratio_early < 1.28
            ):
                # Held pipe: BBR-like max-filter while delay is clean.
                # Cold-start age is huge (last_reconfig_t=-1e9), so the
                # age<0.85 branch never fires without this.
                self.bw_est = max(pct_val, 0.30 * pct_val + 0.70 * max_val)
            else:
                self.bw_est = pct_val
            floor_ref = (
                self._halo_seed_bw
                if self.use_halo and self._halo_seed_bw > 0
                else self.prior_bw
            )
            if floor_ref > 0 and age < 2.0 and not self.fair_mode:
                floor_frac = max(0.38, 0.68 - 0.15 * age)
                if delay_ratio_early < 1.35:
                    self.bw_est = max(self.bw_est, floor_ref * floor_frac)
                elif delay_ratio_early < 1.55:
                    # Soft floor only - do not hard-hold prior under delay risk
                    self.bw_est = max(self.bw_est, floor_ref * floor_frac * 0.72)
            elif floor_ref > 0 and age < 1.5:
                self.bw_est = max(self.bw_est, floor_ref * 0.50)
            if self.hint_capacity_bps > 0:
                self.bw_est = 0.72 * self.bw_est + 0.28 * self.hint_capacity_bps

        if self.bw_est > 0:
            # Reclaim: pacing can stay a bit optimistic; cwnd is delay-capped below.
            # QSP may discount pace from sojourn excess; never changes BDP/cwnd target.
            pace_gain = self._qsp_pace_gain(t, delay_ratio_early, rtt_s)
            if self._pipe_hold_fill(t):
                # BBR startup pacing_gain is 2.77; Crest default is 1.08.
                pace_gain = max(pace_gain, 2.20)
            self.pacing_rate_bps = self.bw_est * pace_gain
        elif self.prior_bw > 0:
            self.pacing_rate_bps = self.prior_bw * 0.65

        # ---- REPROBE two-phase ----
        if t < self.reprobe_until:
            in_b = t >= self.reprobe_phase_b
            self.mode = "reprobe_fill" if in_b else "reprobe_explore"
            growth = (1.42 if in_b else 1.22) * (0.9 if self.fair_mode else 1.0)
            self.cwnd += bytes_acked * growth
            # v3.4-p95: lower fill ceiling so fill does not overshoot into 150-175 ms
            # v3.6 Keel: when live/min RTT inflates vs keel, size ceiling on keel
            ceil_rtt = self.min_rtt if self.min_rtt < 1e17 else 0.0
            if self._keel_rtt > 0 and ceil_rtt > 0 and ceil_rtt > 1.2 * self._keel_rtt:
                ceil_rtt = self._keel_rtt * 1.2
            ceiling = max(80 * MSS, self.prior_bdp * 1.35)
            if self.bw_est > 0 and ceil_rtt > 0:
                ceiling = max(ceiling, 1.55 * self.bw_est * ceil_rtt / 8.0)
            if self.hint_capacity_bps > 0 and ceil_rtt > 0:
                ceiling = max(
                    ceiling, 1.35 * self.hint_capacity_bps * ceil_rtt / 8.0
                )
            # Soft-QIR standing queue: tighten fill if delay already elevated
            if delay_ratio_early > 1.40 and self.bw_est > 0 and ceil_rtt > 0:
                ceiling = min(ceiling, 1.25 * self.bw_est * ceil_rtt / 8.0)
            self.cwnd = min(self.cwnd, ceiling)
            # Early exit: stable fill OR delay building during fill
            delay_exit = (
                in_b
                and self.min_rtt < 1e17
                and delay_ratio_early > 1.55
                and self.stable_acks >= 1
            )
            if (
                in_b
                and self.bw_est > 0
                and self.min_rtt < 1e17
                and self.rtt_var_ewma < 0.32 * max(self.min_rtt, 0.02)
            ):
                self.stable_acks += 1
            if delay_exit or (in_b and self.stable_acks >= 2):
                self.reprobe_until = t
                self.mode = "cruise"
                self.ssthresh = self.cwnd
                rtt_ref = self.min_rtt if self.min_rtt < 1e17 else 0.04
                self._reclaim_until = t + max(0.15, 2.5 * rtt_ref)
                self._commit_cwnd = self.cwnd  # 2PC commit point
                if self.bw_est > 0:
                    self._remember_epoch_bw(self.bw_est)
                # Arm Orbit Pulse clock after settle (no aggressive PLL reclaim)
                if self.use_orbit_pulse and not self.fair_mode:
                    self._pulse_cycle_t = t
            return

        if lost > 0 and self.min_rtt < 1e17 and rtt_s > 1.45 * self.min_rtt:
            self.consec_loss += 1
        else:
            self.consec_loss = 0

        sizing_rtt = self.min_rtt if self.min_rtt < 1e17 else max(rtt_s, 0.02)
        if len(self.rtt_hist) >= 8 and self.min_rtt < 1e17:
            recent_med = self._median(list(self.rtt_hist)[-8:])
            # Soft sizing bias toward recent median under delay risk (no min death spiral)
            if recent_med > 1.7 * self.min_rtt:
                sizing_rtt = 0.32 * self.min_rtt + 0.68 * recent_med
            elif recent_med > 1.25 * self.min_rtt:
                sizing_rtt = 0.55 * self.min_rtt + 0.45 * recent_med
            else:
                sizing_rtt = 0.72 * self.min_rtt + 0.28 * recent_med
        bdp = 10 * MSS
        if sizing_rtt > 0 and self.bw_est > 0:
            bdp = self.bw_est * sizing_rtt / 8.0

        path_floor = sizing_rtt
        if len(self.rtt_hist) >= 12:
            path_floor = max(min(list(self.rtt_hist)[-12:]), sizing_rtt * 0.85)
        delay_ratio = rtt_s / max(path_floor, 1e-4)
        if delay_ratio > 1.40:
            self.high_delay_streak += 1
        else:
            self.high_delay_streak = max(0, self.high_delay_streak - 1)
        crest = self._crest_hit(t, rtt_s, delay_ratio)

        if self.cwnd < self.ssthresh or self.mode in (
            "startup",
            "reprobe_explore",
            "reprobe_fill",
            "mobility_loss",
            "ascent_freeze",
        ):
            self.mode = "startup"
            if self._pipe_hold_active():
                # BBR startup is +2× ACKed; Crest 1.28× is the ~6 Mbps 25s tax
                # on a held ~400 Mbps pipe (w1 first 25s = entire 90s gap).
                growth = 1.92
            else:
                growth = 1.15 if self.fair_mode else 1.28
            self.cwnd += bytes_acked * growth
            # Cap startup overshoot when delay is already elevated
            if delay_ratio > 1.45 and self.bw_est > 0:
                self.cwnd = min(self.cwnd, bdp * 1.08)
            if self._pipe_hold_active() and self.bw_est > 0:
                # 25s probe: uncapped 1.92× grew cwnd to 17 MB by t=2 and
                # congestive-cut. BBR caps at ~4× BDP; 2.2× is enough to
                # fill a 1 MB buffer on a ~400 Mbps / 59 ms pipe.
                self.cwnd = min(self.cwnd, max(bdp * 2.20, 20 * MSS))
            if self.cwnd >= bdp * 0.88 and self.bw_est > 0:
                self.mode = "cruise"
                self.ssthresh = self.cwnd
        else:
            # fair_mode: AIMD-ish around 1.0x BDP; else mild probe with delay-aware cap
            # v3.5/v3.6 TBPR + Keel 2PC: short post-hop reclaim if delay clean
            age = t - self.last_reconfig_t
            keel_ratio = (
                rtt_s / self._keel_rtt if self._keel_rtt > 0 else delay_ratio
            )
            if self._reclaim_until < 0 and 0.15 < age < 1.0:
                rtt_ref = self.min_rtt if self.min_rtt < 1e17 else 0.04
                self._reclaim_until = t + max(0.15, 2.5 * rtt_ref)
                if self._commit_cwnd <= 0:
                    self._commit_cwnd = self.cwnd
            # v3.9 CA-hard: abort TBPR/OCE on crest (cruise/reclaim only)
            if crest:
                self._apply_crest_abort(t, bdp)
            # Abort + optional rollback if delay or keel sight sees queue risk
            if delay_ratio > 1.28 or keel_ratio > 1.38:
                if (
                    self._commit_cwnd > 0
                    and t < self._reclaim_until
                    and self.cwnd > self._commit_cwnd * 1.05
                    and (delay_ratio > 1.40 or keel_ratio > 1.45)
                ):
                    self.cwnd = max(4 * MSS, self._commit_cwnd)
                    self.keel_rollbacks += 1
                self._reclaim_until = min(self._reclaim_until, t)
                self._pulse_until = min(self._pulse_until, t)
                self._commit_cwnd = 0.0
            # Very-clean post-hop: slightly stronger reclaim target
            clean_boost = (
                not self.fair_mode
                and t < self._reclaim_until
                and delay_ratio < 1.12
                and keel_ratio < 1.15
                and self.high_delay_streak == 0
                and not crest
            )
            reclaim = (
                not self.fair_mode
                and t < self._reclaim_until
                and delay_ratio < 1.18
                and keel_ratio < 1.25
                and self.high_delay_streak == 0
                and not crest
            )
            delay_clean = (
                delay_ratio < 1.18
                and self.high_delay_streak == 0
                and not crest
            )
            # v3.10 Orbit Pulse: BBR-like probe every ~8 RTT in clean cruise
            rtt_ref_pulse = self.min_rtt if self.min_rtt < 1e17 else 0.04
            if (
                self.use_orbit_pulse
                and not self.fair_mode
                and t >= self.reprobe_until
                and t >= self._ca_hold_until
                and delay_clean
                and delay_ratio < 1.14
                and age > 0.5
            ):
                if self._pulse_cycle_t <= 0:
                    self._pulse_cycle_t = t
                if t - self._pulse_cycle_t >= 8.0 * rtt_ref_pulse:
                    self._pulse_until = t + max(0.03, 1.0 * rtt_ref_pulse)
                    self._pulse_cycle_t = t
                    self.orbit_pulses += 1
            if crest or delay_ratio > 1.28:
                self._pulse_until = min(self._pulse_until, t)
            pulse_active = (
                self.use_orbit_pulse
                and not self.fair_mode
                and t < self._pulse_until
                and not crest
            )
            lsg_ok = self._lsg_surplus_ok(t, delay_ratio)
            if self.fair_mode:
                target = 1.02 * bdp
            elif self.use_dlc:
                # Dual-Ledger: safe vs tide. Fly tide only if delay clean, no
                # crest, and LSG surplus. Stretch cap ≤ 1.42× BDP. Not DTCE.
                # Orbit Pulse may briefly lift tide toward 1.42× (BBR-like).
                cwnd_safe = 1.08 * bdp
                if delay_ratio > 1.55 or self.high_delay_streak >= 3:
                    cwnd_safe = 1.05 * bdp
                elif delay_ratio > 1.35:
                    cwnd_safe = 1.08 * bdp
                if t < self._oce_until and delay_ratio < 1.14:
                    cwnd_tide = 1.42 * bdp
                elif clean_boost or (
                    reclaim and delay_ratio < 1.15 and keel_ratio < 1.18
                ):
                    cwnd_tide = 1.38 * bdp
                elif reclaim:
                    cwnd_tide = 1.28 * bdp
                elif delay_ratio < 1.18:
                    cwnd_tide = 1.32 * bdp
                else:
                    cwnd_tide = 1.20 * bdp
                if pulse_active and delay_clean:
                    cwnd_tide = max(cwnd_tide, min(1.42 * bdp, cwnd_tide * 1.22))
                cwnd_tide = min(cwnd_tide, 1.42 * bdp)
                would_tide = delay_clean
                if would_tide and not lsg_ok:
                    self.lsg_clamps += 1
                fly_tide = would_tide and lsg_ok and t >= self._ca_hold_until
                if fly_tide:
                    target = cwnd_tide
                    self.dlc_tide_flights += 1
                else:
                    target = cwnd_safe
            elif delay_ratio > 1.55 or self.high_delay_streak >= 3:
                target = 1.05 * bdp
            elif delay_ratio > 1.35:
                target = 1.10 * bdp
            elif clean_boost or (
                reclaim and delay_ratio < 1.15 and keel_ratio < 1.18
            ):
                target = 1.38 * bdp
            elif reclaim:
                target = 1.28 * bdp
            elif delay_ratio < 1.18 and self.high_delay_streak == 0 and not self.fair_mode:
                # v3.6 clean-cruise: compete with BBR gain on OPE-fair paths
                target = 1.38 * bdp
            else:
                target = 1.18 * bdp
            # Freeze-only anticipator: hold growth, never suppress detect
            anticipator_hold = (
                self.use_anticipator
                and not self.fair_mode
                and t < self._anticipator_until
                and t >= self.reprobe_until
            )
            skypulse_hold = (
                self.hint_freeze_only
                and not self.fair_mode
                and t < self.freeze_until
                and t >= self.reprobe_until
            )
            if anticipator_hold or skypulse_hold:
                target = min(target, self.cwnd)
            if self.fair_mode and (delay_ratio > 1.45 or self.high_delay_streak >= 3):
                self.cwnd = max(4 * MSS, self.cwnd * 0.92)
                self.mode = "fair_yield"
            elif delay_ratio > 1.85 or self.high_delay_streak >= 5:
                # Strong yield when queue risk is high
                self.cwnd = max(4 * MSS, self.cwnd * 0.96)
                self.mode = "delay_yield"
            elif delay_ratio > 1.45:
                # Early mild yield (v3.3-A only acted above 2.0)
                self.cwnd = max(4 * MSS, self.cwnd - MSS * 0.35)
                if self.cwnd > target:
                    self.cwnd = max(4 * MSS, min(self.cwnd, target * 1.05))
                self.mode = "delay_yield"
            elif skypulse_hold:
                self.mode = "skypulse_freeze"
            elif anticipator_hold:
                self.mode = "anticipator_freeze"
            elif self.cwnd < target:
                if self.fair_mode:
                    step = MSS * 0.45
                elif pulse_active and target >= 1.28 * bdp:
                    step = MSS * 1.30
                elif target >= 1.30 * bdp:
                    step = MSS * 1.20
                elif reclaim:
                    step = MSS * 1.10
                else:
                    step = MSS * 0.90
                self.cwnd += step
                self.mode = "orbit_pulse" if pulse_active else "cruise"
            if pulse_active and self.bw_est > 0 and delay_clean:
                self.pacing_rate_bps = max(self.pacing_rate_bps, self.bw_est * 1.22)
            elif self.cwnd > target * 1.12:
                self.cwnd -= MSS * (0.2 if self.fair_mode else 0.18)
                self.mode = "cruise"
            else:
                self.mode = "cruise"

            # v3.7 Orbit Capacity Echo: after SER, chase live delivery if delay clean
            if (
                not self.fair_mode
                and t < self._oce_until
                and self.bw_est > 0
                and not crest
                and not anticipator_hold
            ):
                if delay_ratio > 1.30:
                    if self._oce_commit > 0 and self.cwnd > self._oce_commit * 1.05:
                        self.cwnd = max(4 * MSS, self._oce_commit)
                    self._oce_until = t
                elif delay_ratio < 1.14 and self.high_delay_streak == 0:
                    rate = self._delivery_rate_sample(t)
                    if rate > self.bw_est * 1.01:
                        self.bw_est = 0.65 * self.bw_est + 0.35 * rate
                        if sizing_rtt > 0:
                            bdp = self.bw_est * sizing_rtt / 8.0
                    oce_target = 1.42 * bdp
                    if self.cwnd < oce_target:
                        self.cwnd += MSS * 1.35
                        self.pacing_rate_bps = max(
                            self.pacing_rate_bps, self.bw_est * 1.12
                        )
                        if self.mode != "oce_echo":
                            self.oce_echos += 1
                        self.mode = "oce_echo"

            # Hard cap above ~1.08x BDP when delay risk present
            if delay_ratio > 1.35 and self.bw_est > 0:
                self.cwnd = min(self.cwnd, bdp * 1.08)
            if self._pipe_hold_active() and self.bw_est > 0:
                self.cwnd = min(self.cwnd, max(bdp * 2.20, 20 * MSS))
            self.cwnd = max(4 * MSS, self.cwnd)
            # v3.6: adopt keel toward healthy cruise min (downward or mild up)
            if self.min_rtt < 1e17 and age > 1.5 and self._keel_rtt > 0:
                if self.min_rtt < self._keel_rtt:
                    self._keel_rtt = 0.7 * self._keel_rtt + 0.3 * self.min_rtt
                elif self.min_rtt < 1.2 * self._keel_rtt and delay_ratio < 1.2:
                    self._keel_rtt = 0.88 * self._keel_rtt + 0.12 * self.min_rtt

        self._prev_delay_ratio = delay_ratio

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
        # Held pipe: BBR ignores loss; Crest's 0.72 cut is the t=12 recovery
        # hole on WetLinks (capacity held, spike is ping_worst not a cap hop).
        if self._pipe_hold_active() and self.min_rtt < 1e17:
            recent = self.rtt_hist[-1] if self.rtt_hist else 0.0
            if recent <= 0.0 or recent < 1.55 * self.min_rtt:
                self.mode = "pipe_hold_loss"
                return
        # True congestion: slightly milder than CUBIC for multi-flow friendliness
        self.ssthresh = max(4 * MSS, self.cwnd * 0.72)
        self.cwnd = self.ssthresh
        self.pacing_rate_bps = max(
            self.pacing_rate_bps * 0.7,
            self.cwnd * 8 / max(self.min_rtt if self.min_rtt < 1e17 else 0.05, 0.02),
        )
        self.mode = "congestive_recovery"
