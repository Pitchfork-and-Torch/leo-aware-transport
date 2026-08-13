"""
Starlink-class LEO path dynamics.

Models what breaks classic CCAs: periodic handovers, abrupt RTT jumps,
capacity changes, and non-congestive loss bursts correlated with path changes.

Supports optional CSV trace replay (t_s,rtt_ms,capacity_mbps[,loss_p][,reconfig]).
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Optional
import csv
import math
import random


@dataclass
class PathState:
    """Instantaneous path properties seen by the endpoint / ASCENT side channel."""

    rtt_s: float
    capacity_bps: float
    loss_p: float
    reconfigured: bool = False
    epoch: int = 0
    # ASCENT-style freeze window (seconds remaining; 0 = none)
    freeze_remaining_s: float = 0.0
    freeze_active: bool = False
    # Optional predicted post-hop capacity (for assisted controllers)
    next_capacity_bps: float = 0.0


@dataclass
class LeoPathConfig:
    """Configurable LEO-like dynamics.

    Entities (conceptual): ground terminal -> LEO satellite -> (optional ISL) ->
    ground station -> Internet. This path object abstracts the end-to-end
    bottleneck and delay as seen by a single (or shared) flow.
    """

    duration_s: float = 120.0
    dt_s: float = 0.01  # simulation slot
    # Handover / reconfiguration (Starlink-class: often every 15-60s)
    handover_interval_s: float = 25.0
    handover_jitter_s: float = 8.0
    # RTT regime (seconds) - base ~20-100+ ms with abrupt jumps
    rtt_base_s: float = 0.035
    rtt_jump_min_s: float = 0.02
    rtt_jump_max_s: float = 0.09
    # Capacity (bits per second)
    capacity_min_bps: float = 20e6
    capacity_max_bps: float = 120e6
    # Non-congestive loss around reconfiguration
    reconfig_loss_burst_p: float = 0.08
    reconfig_loss_window_s: float = 0.4
    steady_loss_p: float = 0.0005
    # Buffer (bytes) at bottleneck - queue overflow = congestive loss
    buffer_bytes: int = 250_000
    seed: int = 7
    terrestrial: bool = False  # if True, stable path for comparison
    # Optional simplified ISL hop: adds extra RTT variance when True
    isl_enabled: bool = False
    isl_extra_rtt_s: float = 0.008
    # Pre-handover freeze window (ASCENT can signal this)
    freeze_lead_s: float = 0.12
    freeze_trail_s: float = 0.18
    # Optional CSV trace path (relative or absolute)
    trace_csv: Optional[str] = None
    # Path generative profile. Default ope_v36 is frozen (suite / product lock).
    # starlink_rtt / starlink_v1 are opt-in realism probes — they must not
    # silently replace the OPE-era lock.
    path_profile: str = "ope_v36"


@dataclass
class TraceSample:
    t_s: float
    rtt_s: float
    capacity_bps: float
    loss_p: float
    reconfig: bool


# Opt-in Starlink-inspired capacity band (starlink_v1 only). Not the suite default.
STARLINK_V1_CAP_MIN_BPS = 40e6
STARLINK_V1_CAP_MAX_BPS = 150e6


def _pct(xs: list[float], p: float) -> float:
    if not xs:
        return float("nan")
    s = sorted(xs)
    if len(s) == 1:
        return s[0]
    k = (p / 100.0) * (len(s) - 1)
    lo = int(math.floor(k))
    hi = int(math.ceil(k))
    if lo == hi:
        return s[lo]
    w = k - lo
    return s[lo] * (1.0 - w) + s[hi] * w


def walk_path_geometry(cfg: LeoPathConfig) -> dict:
    """Time-weighted path geometry (no CCA). Used by Step 0 feasibility."""
    path = LeoPath(cfg)
    rtts: list[float] = []
    caps: list[float] = []
    losses: list[float] = []
    steps = int(cfg.duration_s / cfg.dt_s)
    oracle_bits = 0.0
    for _ in range(steps):
        st = path.step()
        rtts.append(st.rtt_s)
        caps.append(st.capacity_bps)
        losses.append(st.loss_p)
        oracle_bits += st.capacity_bps * cfg.dt_s * (1.0 - st.loss_p)
    n = max(len(rtts), 1)
    # Capacity-weighted RTT (ACK p95 if the pipe is always full)
    weighted: list[float] = []
    for r, c in zip(rtts, caps):
        copies = max(1, int(round(c / 1e6)))
        weighted.extend([r] * copies)
    oracle_gp_mbps = oracle_bits / max(cfg.duration_s, 1e-9) / 1e6
    mean_cap_mbps = (sum(caps) / n) / 1e6
    return {
        "seed": cfg.seed,
        "profile": cfg.path_profile,
        "handovers": list(path.handover_times),
        "n_ho": len(path.handover_times),
        "mean_cap_mbps": mean_cap_mbps,
        "min_cap_mbps": min(caps) / 1e6,
        "max_cap_mbps": max(caps) / 1e6,
        "oracle_gp_mbps": oracle_gp_mbps,
        "path_p50_ms": _pct(rtts, 50) * 1000,
        "path_p95_ms": _pct(rtts, 95) * 1000,
        "path_p99_ms": _pct(rtts, 99) * 1000,
        "path_max_ms": max(rtts) * 1000,
        "cap_weighted_p95_ms": _pct(weighted, 95) * 1000,
        "frac_cap_ge_75": sum(1 for c in caps if c >= 75e6) / n,
        "mean_loss_p": sum(losses) / n,
    }


def load_trace_csv(path: str | Path) -> list[TraceSample]:
    """Load Starlink-like path trace.

    Required columns (case-insensitive):
      t_s OR time_s OR t
      rtt_ms OR rtt_s
      capacity_mbps OR capacity_bps OR bw_mbps OR cubic_goodput_mbps
    Optional: loss_p, reconfig (0/1)

    `cubic_goodput_mbps` is a capacity alias used by the zhao_zenodo23 research
    era: TCP Cubic downlink goodput (lower bound), not dish PHY / UDP sat.
    """
    path = Path(path)
    rows: list[TraceSample] = []
    with path.open(encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        if not reader.fieldnames:
            raise ValueError(f"empty trace: {path}")
        fields = {h.lower().strip(): h for h in reader.fieldnames}

        def col(*names: str) -> Optional[str]:
            for n in names:
                if n in fields:
                    return fields[n]
            return None

        t_key = col("t_s", "time_s", "t", "time")
        rtt_key = col("rtt_ms", "rtt_s", "rtt")
        cap_key = col(
            "capacity_mbps",
            "bw_mbps",
            "capacity_bps",
            "bw_bps",
            "cubic_goodput_mbps",
        )
        loss_key = col("loss_p", "loss", "loss_rate")
        rec_key = col("reconfig", "handover", "reconfigured")
        if not t_key or not rtt_key or not cap_key:
            raise ValueError(
                f"trace {path} needs t, rtt, capacity columns; got {reader.fieldnames}"
            )
        for raw in reader:
            t = float(raw[t_key])
            rtt_raw = float(raw[rtt_key])
            # Heuristic: values > 2 treated as milliseconds
            rtt_s = rtt_raw / 1000.0 if rtt_raw > 2.0 or "ms" in rtt_key.lower() else rtt_raw
            cap_raw = float(raw[cap_key])
            if "mbps" in cap_key.lower() or cap_raw < 1e5:
                cap_bps = cap_raw * 1e6
            else:
                cap_bps = cap_raw
            loss_p = float(raw[loss_key]) if loss_key and raw.get(loss_key) not in (None, "") else 0.0005
            reconfig = False
            if rec_key and raw.get(rec_key) not in (None, ""):
                reconfig = str(raw[rec_key]).strip().lower() in ("1", "true", "yes", "y")
            rows.append(
                TraceSample(
                    t_s=t,
                    rtt_s=rtt_s,
                    capacity_bps=cap_bps,
                    loss_p=loss_p,
                    reconfig=reconfig,
                )
            )
    if not rows:
        raise ValueError(f"no samples in {path}")
    rows.sort(key=lambda s: s.t_s)
    return rows


def generate_synthetic_starlink_trace(
    path: str | Path,
    duration_s: float = 90.0,
    dt_s: float = 0.05,
    seed: int = 13,
    handover_interval_s: float = 12.0,
    path_profile: str = "ope_v36",
) -> Path:
    """Write a synthetic Starlink-class CSV for offline replay demos."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    cfg = LeoPathConfig(
        duration_s=duration_s,
        dt_s=dt_s,
        seed=seed,
        handover_interval_s=handover_interval_s,
        handover_jitter_s=4.0,
        path_profile=path_profile,
    )
    # Use generative model at finer step then downsample rows
    gen = LeoPath(cfg)
    with path.open("w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(["t_s", "rtt_ms", "capacity_mbps", "loss_p", "reconfig"])
        steps = int(duration_s / dt_s)
        for _ in range(steps):
            st = gen.step()
            t_now = max(0.0, gen.t - cfg.dt_s)
            w.writerow(
                [
                    f"{t_now:.4f}",
                    f"{st.rtt_s * 1000:.3f}",
                    f"{st.capacity_bps / 1e6:.4f}",
                    f"{st.loss_p:.6f}",
                    1 if st.reconfigured else 0,
                ]
            )
    return path


class LeoPath:
    """Time-varying LEO path generator (synthetic or CSV-driven)."""

    def __init__(self, cfg: LeoPathConfig):
        self.cfg = cfg
        self.rng = random.Random(cfg.seed)
        self.t = 0.0
        self.epoch = 0
        self._next_ho = self._sample_ho_time(0.0)
        self._rtt = cfg.rtt_base_s
        self._cap = (cfg.capacity_min_bps + cfg.capacity_max_bps) / 2
        self._reconfig_until = -1.0
        self._freeze_until = -1.0
        self._next_cap = 0.0
        self._ho_spike_until = -1.0
        self._ho_spike_s = 0.0
        self.handover_times: list[float] = []
        self._trace: Optional[list[TraceSample]] = None
        self._trace_i = 0
        if cfg.trace_csv:
            self._trace = load_trace_csv(cfg.trace_csv)
            # duration from trace if longer
            last_t = self._trace[-1].t_s
            if last_t > 0 and cfg.duration_s > last_t + cfg.dt_s:
                # keep cfg duration; trace will clamp at end
                pass
        if cfg.terrestrial and not cfg.trace_csv:
            self._rtt = 0.04
            self._cap = 80e6
            self._next_ho = float("inf")
        elif (cfg.path_profile or "ope_v36").lower() == "starlink_v1" and not cfg.trace_csv:
            self._cap = (STARLINK_V1_CAP_MIN_BPS + STARLINK_V1_CAP_MAX_BPS) / 2

    def _sample_ho_time(self, after: float) -> float:
        c = self.cfg
        return after + c.handover_interval_s + self.rng.uniform(
            -c.handover_jitter_s, c.handover_jitter_s
        )

    def _draw_epoch_rtt_cap(self) -> tuple[float, float]:
        """Consume RNG for the next epoch (rtt, cap). Shared by peek + reconfigure.

        ope_v36 draw order is frozen (must stay bit-identical to v3.6/v3.7).
        starlink_* profiles use a different sequence on purpose.
        """
        c = self.cfg
        profile = (c.path_profile or "ope_v36").lower()
        if profile in ("starlink_rtt", "starlink_v1"):
            # Cruise RTT in a Starlink-like 40-75 ms band; rare sat ~50-100 ms.
            # HO transients are applied separately (not epoch-sticky).
            rtt = 0.030 + self.rng.uniform(0.010, 0.045)
            if self.rng.random() < 0.12:
                rtt += self.rng.uniform(0.010, 0.025)
            if c.isl_enabled:
                rtt += c.isl_extra_rtt_s * self.rng.uniform(0.5, 2.0)
            cap_lo = (
                STARLINK_V1_CAP_MIN_BPS if profile == "starlink_v1" else c.capacity_min_bps
            )
            cap_hi = (
                STARLINK_V1_CAP_MAX_BPS if profile == "starlink_v1" else c.capacity_max_bps
            )
            cap = self.rng.uniform(cap_lo, cap_hi)
            return rtt, cap
        rtt = c.rtt_base_s + self.rng.uniform(c.rtt_jump_min_s, c.rtt_jump_max_s)
        if self.rng.random() < 0.25:
            rtt += self.rng.uniform(0.03, 0.08)
        if c.isl_enabled:
            rtt += c.isl_extra_rtt_s * self.rng.uniform(0.5, 2.0)
        cap = self.rng.uniform(c.capacity_min_bps, c.capacity_max_bps)
        return rtt, cap

    def _peek_next_path(self) -> tuple[float, float]:
        """Non-consuming peek of next hop RTT/cap (honest ASCENT freeze-lead).

        Uses the same draw sequence as `_do_reconfigure` but restores RNG state
        so multi-seed path identity stays identical to endpoint-only runs.
        """
        st = self.rng.getstate()
        rtt, cap = self._draw_epoch_rtt_cap()
        self.rng.setstate(st)
        return rtt, cap

    def _do_reconfigure(self) -> None:
        c = self.cfg
        self.epoch += 1
        self.handover_times.append(self.t)
        self._rtt, self._cap = self._draw_epoch_rtt_cap()
        profile = (c.path_profile or "ope_v36").lower()
        if profile in ("starlink_rtt", "starlink_v1"):
            # Brief HO RTT spike (loss window), not a 12s high-RTT epoch.
            self._ho_spike_s = self.rng.uniform(0.020, 0.055)
            self._ho_spike_until = self.t + c.reconfig_loss_window_s
        else:
            self._ho_spike_s = 0.0
            self._ho_spike_until = -1.0
        self._next_cap = self._cap
        self._reconfig_until = self.t + c.reconfig_loss_window_s
        self._freeze_until = self.t + c.freeze_trail_s
        self._next_ho = self._sample_ho_time(self.t)

    def _step_trace(self) -> PathState:
        assert self._trace is not None
        # Advance index to last sample with t_s <= self.t
        while (
            self._trace_i + 1 < len(self._trace)
            and self._trace[self._trace_i + 1].t_s <= self.t + 1e-12
        ):
            self._trace_i += 1
        s = self._trace[self._trace_i]
        reconfigured = s.reconfig
        if reconfigured:
            # Only fire once per sample
            if self._trace_i not in getattr(self, "_trace_fired", set()):
                if not hasattr(self, "_trace_fired"):
                    self._trace_fired = set()
                self._trace_fired.add(self._trace_i)
                self.epoch += 1
                self.handover_times.append(self.t)
                self._freeze_until = self.t + self.cfg.freeze_trail_s
                self._reconfig_until = self.t + self.cfg.reconfig_loss_window_s
                self._next_cap = s.capacity_bps
            else:
                reconfigured = False
        freeze_rem = max(0.0, self._freeze_until - self.t)
        # Pre-next reconfig freeze: look ahead for upcoming reconfig sample
        lead = self.cfg.freeze_lead_s
        for j in range(self._trace_i + 1, min(self._trace_i + 50, len(self._trace))):
            if self._trace[j].reconfig:
                dt = self._trace[j].t_s - self.t
                if 0 < dt <= lead:
                    freeze_rem = max(freeze_rem, dt)
                    self._next_cap = self._trace[j].capacity_bps
                break
        st = PathState(
            rtt_s=s.rtt_s,
            capacity_bps=s.capacity_bps,
            loss_p=s.loss_p,
            reconfigured=reconfigured,
            epoch=self.epoch,
            freeze_remaining_s=freeze_rem,
            freeze_active=freeze_rem > 0,
            next_capacity_bps=self._next_cap,
        )
        self.t += self.cfg.dt_s
        return st

    def step(self) -> PathState:
        if self._trace is not None:
            return self._step_trace()

        c = self.cfg
        reconfigured = False
        # Pre-handover freeze lead with honest next_capacity peek (v3.1)
        peek_cap = 0.0
        if (
            not c.terrestrial
            and self._next_ho < float("inf")
            and 0 < self._next_ho - self.t <= c.freeze_lead_s
        ):
            self._freeze_until = max(
                self._freeze_until, self._next_ho + c.freeze_trail_s
            )
            _, peek_cap = self._peek_next_path()
            self._next_cap = peek_cap
        if not c.terrestrial and self.t >= self._next_ho:
            self._do_reconfigure()
            reconfigured = True

        if not c.terrestrial:
            flicker = 1.0 + 0.03 * math.sin(self.t * 1.7 + self.epoch)
            profile = (c.path_profile or "ope_v36").lower()
            cap_floor = (
                STARLINK_V1_CAP_MIN_BPS * 0.5
                if profile == "starlink_v1"
                else c.capacity_min_bps * 0.5
            )
            cap = max(cap_floor, self._cap * flicker)
        else:
            cap = self._cap

        if self.t < self._reconfig_until:
            loss_p = c.reconfig_loss_burst_p
        else:
            loss_p = c.steady_loss_p

        rtt = self._rtt
        if self.t < self._ho_spike_until:
            rtt += self._ho_spike_s

        freeze_rem = max(0.0, self._freeze_until - self.t)
        st = PathState(
            rtt_s=rtt,
            capacity_bps=cap,
            loss_p=loss_p,
            reconfigured=reconfigured,
            epoch=self.epoch,
            freeze_remaining_s=freeze_rem,
            freeze_active=freeze_rem > 0,
            next_capacity_bps=self._next_cap if freeze_rem > 0 or reconfigured else 0.0,
        )
        self.t += c.dt_s
        return st
