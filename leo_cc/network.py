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


@dataclass
class TraceSample:
    t_s: float
    rtt_s: float
    capacity_bps: float
    loss_p: float
    reconfig: bool


def load_trace_csv(path: str | Path) -> list[TraceSample]:
    """Load Starlink-like path trace.

    Required columns (case-insensitive):
      t_s OR time_s OR t
      rtt_ms OR rtt_s
      capacity_mbps OR capacity_bps OR bw_mbps
    Optional: loss_p, reconfig (0/1)
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
        cap_key = col("capacity_mbps", "bw_mbps", "capacity_bps", "bw_bps")
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

    def _sample_ho_time(self, after: float) -> float:
        c = self.cfg
        return after + c.handover_interval_s + self.rng.uniform(
            -c.handover_jitter_s, c.handover_jitter_s
        )

    def _peek_next_path(self) -> tuple[float, float]:
        """Non-consuming peek of next hop RTT/cap (honest ASCENT freeze-lead).

        Uses the same draw sequence as `_do_reconfigure` but restores RNG state
        so multi-seed path identity stays identical to endpoint-only runs.
        """
        c = self.cfg
        st = self.rng.getstate()
        rtt = c.rtt_base_s + self.rng.uniform(c.rtt_jump_min_s, c.rtt_jump_max_s)
        if self.rng.random() < 0.25:
            rtt += self.rng.uniform(0.03, 0.08)
        if c.isl_enabled:
            rtt += c.isl_extra_rtt_s * self.rng.uniform(0.5, 2.0)
        cap = self.rng.uniform(c.capacity_min_bps, c.capacity_max_bps)
        self.rng.setstate(st)
        return rtt, cap

    def _do_reconfigure(self) -> None:
        c = self.cfg
        self.epoch += 1
        self.handover_times.append(self.t)
        self._rtt = c.rtt_base_s + self.rng.uniform(c.rtt_jump_min_s, c.rtt_jump_max_s)
        if self.rng.random() < 0.25:
            self._rtt += self.rng.uniform(0.03, 0.08)
        if c.isl_enabled:
            self._rtt += c.isl_extra_rtt_s * self.rng.uniform(0.5, 2.0)
        self._cap = self.rng.uniform(c.capacity_min_bps, c.capacity_max_bps)
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
            cap = max(c.capacity_min_bps * 0.5, self._cap * flicker)
        else:
            cap = self._cap

        if self.t < self._reconfig_until:
            loss_p = c.reconfig_loss_burst_p
        else:
            loss_p = c.steady_loss_p

        freeze_rem = max(0.0, self._freeze_until - self.t)
        st = PathState(
            rtt_s=self._rtt,
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
