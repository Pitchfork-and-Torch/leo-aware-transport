"""
Slot-based transport simulation over LeoPath.

One or more flows share a bottleneck buffer. Each slot:
1) Advance LEO path dynamics
2) CCA decides sends
3) Drain bottleneck by capacity
4) Deliver ACKs after RTT delay; apply congestive vs non-congestive loss

v3.6 physics (Orthogonal Path Entropy + optional soft-QIR):
- Mobility/path RNG is isolated from per-packet loss RNG so a CCA that
  triggers more loss_burst events cannot rewrite the orbital timeline
  (same seed ⇒ identical HO/RTT/cap timeline across CCAs).
- ACK RTT may include a soft-capped bottleneck sojourn (soft-QIR). Default
  weight is modest so delay controllers see queues without rewriting the
  latency floor set by orbital geometry.

Optional control-plane modes (ablation):
- path_hint_mode="direct": call on_path_hint from PathState (legacy)
- path_hint_mode="ascent_d": encode PathState as ASCENT-D, decode fail-closed
- path_hint_mode="ascent_plain": unprotected ASCII unit (no RS)
- path_hint_mode="none": no path hints (endpoint-only)
- use_orb_telemetry=True: inject synthetic OrbCC signals each slot
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Optional
from collections import defaultdict, deque
import random

from leo_cc.network import LeoPath, LeoPathConfig, PathState
from leo_cc.ccas import BaseCCA, MSS
from leo_cc.ascent_path_hint import (
    encode_path_hint_ascent_d,
    encode_path_hint_unit,
    decode_plain_path_hint,
    ingest_path_hint_stream,
    bit_flip_noise,
    IngestStats,
)
from leo_cc.orb_signals import InNetworkTelemetry


@dataclass
class Packet:
    flow_id: int
    size: int
    send_t: float
    seq: int


@dataclass
class FlowLog:
    t: list = field(default_factory=list)
    cwnd: list = field(default_factory=list)
    inflight: list = field(default_factory=list)
    rtt: list = field(default_factory=list)
    goodput_bps: list = field(default_factory=list)
    loss_events: list = field(default_factory=list)
    mode: list = field(default_factory=list)
    delivered_bytes: float = 0.0
    lost_bytes: float = 0.0
    samples_rtt: list = field(default_factory=list)


@dataclass
class SimResult:
    handovers: list[float]
    flows: list[FlowLog]
    cfg: LeoPathConfig
    cca_names: list[str]
    ascent_ingest: Optional[IngestStats] = None
    orb_samples: int = 0


class Flow:
    def __init__(self, flow_id: int, cca: BaseCCA):
        self.id = flow_id
        self.cca = cca
        self.seq = 0
        self.log = FlowLog()
        self.pending_acks: deque[tuple[float, int, float]] = deque()  # (deliver_t, bytes, send_rtt)
        self.last_goodput_mark = 0.0
        self.bytes_since_mark = 0


def _should_emit_hint(st: PathState, prev_epoch: int, prev_freeze: bool) -> bool:
    """Emit control frames on reconfig or freeze edge (not every freeze slot).

    Full ASCENT-D RS encode every 10 ms slot is too expensive for the research
    harness; edges capture predictive freeze lead + reconfig with low cost.
    """
    freeze_now = bool(st.freeze_active or (st.freeze_remaining_s and st.freeze_remaining_s > 0))
    freeze_edge = freeze_now and not prev_freeze
    return bool(st.reconfigured or freeze_edge or (st.epoch != prev_epoch and st.reconfigured))


def _apply_direct_hint(cca: BaseCCA, t: float, st: PathState) -> None:
    cca.on_path_hint(
        t,
        st.reconfigured,
        capacity_bps=st.capacity_bps if st.reconfigured else None,
        rtt_s=st.rtt_s if (st.reconfigured or st.freeze_active) else None,
        epoch=st.epoch if st.reconfigured else None,
        freeze_remaining_s=st.freeze_remaining_s,
        freeze_active=st.freeze_active,
        next_capacity_bps=st.next_capacity_bps or None,
    )


def run_sim(
    cca_factory: Callable[[], BaseCCA],
    cfg: Optional[LeoPathConfig] = None,
    n_flows: int = 1,
    app_unlimited: bool = True,
    *,
    path_hint_mode: str = "direct",
    ascent_bit_flips: int = 0,
    use_orb_telemetry: bool = False,
    orb_switch_id: int = 0xA11,
) -> SimResult:
    """
    path_hint_mode:
      direct       - call on_path_hint from PathState (default, backward compatible)
      ascent_d     - ASCENT-D encode/decode with erase-on-fail (optional bit flips)
      ascent_plain - unprotected ASCII path-hint units
      none         - no path hints delivered
    """
    cfg = cfg or LeoPathConfig()
    path = LeoPath(cfg)
    flows = [Flow(i, cca_factory()) for i in range(n_flows)]
    buffer: deque[Packet] = deque()
    buffer_bytes = 0
    t = 0.0
    steps = int(cfg.duration_s / cfg.dt_s)
    inflight_pkts: dict[int, int] = defaultdict(int)

    mode = (path_hint_mode or "direct").lower()
    ingest_stats = IngestStats() if mode in ("ascent_d", "ascent_plain") else None
    noise_rng = random.Random(cfg.seed ^ 0xA5CE)
    # Orthogonal Path Entropy (OPE): loss draws must not consume path.rng.
    # Same seed + scenario ⇒ identical HO/RTT/cap timeline across CCAs.
    loss_rng = random.Random(cfg.seed ^ 0x10CC)
    orb = InNetworkTelemetry(switch_id=orb_switch_id) if use_orb_telemetry else None
    orb_samples = 0
    prev_epoch = -1
    prev_freeze = False

    for step in range(steps):
        st: PathState = path.step()
        t = path.t - cfg.dt_s
        freeze_now = bool(
            st.freeze_active or (st.freeze_remaining_s and st.freeze_remaining_s > 0)
        )

        # ---- Control plane: path hints / ASCENT-D ----
        if mode == "none":
            pass
        elif mode == "direct":
            for fl in flows:
                _apply_direct_hint(fl.cca, t, st)
        elif mode in ("ascent_d", "ascent_plain") and _should_emit_hint(
            st, prev_epoch, prev_freeze
        ):
            fields = dict(
                reconfigured=st.reconfigured,
                capacity_bps=st.capacity_bps if st.reconfigured else None,
                rtt_s=st.rtt_s if (st.reconfigured or freeze_now) else None,
                epoch=st.epoch if st.reconfigured else None,
                freeze_remaining_s=st.freeze_remaining_s,
                freeze_active=st.freeze_active or freeze_now,
                next_capacity_bps=st.next_capacity_bps or None,
                role="pilot",
            )
            if mode == "ascent_d":
                frame = encode_path_hint_ascent_d(**fields)
                if ascent_bit_flips > 0:
                    frame = bit_flip_noise(frame, ascent_bit_flips, noise_rng)
                for fl in flows:
                    ingest_path_hint_stream(
                        fl.cca, frame, t, stats=ingest_stats
                    )
            else:
                unit = encode_path_hint_unit(**fields)
                hint = decode_plain_path_hint(unit)
                if ingest_stats is not None:
                    ingest_stats.ok += 1
                for fl in flows:
                    if hasattr(fl.cca, "use_path_hints") and not fl.cca.use_path_hints:
                        continue
                    fl.cca.on_path_hint(
                        t,
                        hint.reconfigured,
                        capacity_bps=hint.capacity_bps,
                        rtt_s=hint.rtt_s,
                        epoch=hint.epoch,
                        freeze_remaining_s=hint.freeze_remaining_s,
                        freeze_active=hint.freeze_active,
                        next_capacity_bps=hint.next_capacity_bps,
                    )
                    if ingest_stats is not None:
                        ingest_stats.applied += 1

        prev_epoch = st.epoch
        prev_freeze = freeze_now

        # Deliver due ACKs (RTT sample frozen at drain: path + queue sojourn)
        for fl in flows:
            while fl.pending_acks and fl.pending_acks[0][0] <= t:
                _deliver_t, nbytes, rtt_sample = fl.pending_acks.popleft()
                rtt_sample = max(1e-4, rtt_sample)
                fl.cca.on_ack(t, rtt_sample, nbytes, lost=0)
                fl.log.delivered_bytes += nbytes
                fl.bytes_since_mark += nbytes
                fl.log.samples_rtt.append(rtt_sample)
                inflight_pkts[fl.id] = max(0, inflight_pkts[fl.id] - 1)

        # Drain bottleneck
        drain_budget = st.capacity_bps * cfg.dt_s / 8.0  # bytes
        drained = 0.0
        while buffer and drained + buffer[0].size <= drain_budget + 1e-9:
            pkt = buffer.popleft()
            buffer_bytes -= pkt.size
            drained += pkt.size
            fl = flows[pkt.flow_id]
            # OPE: mobility loss uses loss_rng, never path.rng
            if loss_rng.random() < st.loss_p:
                fl.log.lost_bytes += pkt.size
                # on_loss already accounts for inflight via on_delivered
                fl.cca.on_loss(t, pkt.size, congestive=False)
                inflight_pkts[fl.id] = max(0, inflight_pkts[fl.id] - 1)
                fl.log.loss_events.append((t, "mobility"))
            else:
                # Soft Queue-Inclusive RTT (soft-QIR):
                # rtt = path_base + min(cap, alpha * sojourn). Alpha kept low so
                # orbital geometry still sets the latency floor; delay CCAs still
                # observe standing-queue inflation.
                sojourn_s = max(0.0, t - pkt.send_t)
                q_rtt_s = min(0.025, 0.20 * sojourn_s)
                rtt_sample = st.rtt_s + q_rtt_s
                fl.pending_acks.append((t + st.rtt_s, pkt.size, rtt_sample))

        if orb is not None:
            orb.on_drain(drained)

        # ---- OrbCC-style telemetry (after drain so qLen/tx are fresh) ----
        if orb is not None:
            sig = orb.sample(
                t,
                epoch=st.epoch,
                capacity_bps=st.capacity_bps,
                rtt_s=st.rtt_s,
                qlen_bytes=buffer_bytes,
                flow_cnt=n_flows,
                reconfigured=st.reconfigured,
            )
            for fl in flows:
                fl.cca.on_orb_signal(t, sig)
            orb_samples += 1

        # Sender transmits (paced near fair share of instantaneous capacity)
        for fl in flows:
            can = fl.cca.can_send(t)
            # Cap per-slot inject; multi-flow slightly tighter for fairness experiments
            share = 2.0 if n_flows > 1 else 2.5
            fair_bytes = max(MSS, (st.capacity_bps * cfg.dt_s / 8.0) / max(1, n_flows))
            send_budget = min(can, int(fair_bytes * share))
            while send_budget >= MSS:
                # congestive drop if buffer full
                if buffer_bytes + MSS > cfg.buffer_bytes:
                    fl.cca.on_loss(t, MSS, congestive=True)
                    fl.log.lost_bytes += MSS
                    fl.log.loss_events.append((t, "congestive"))
                    break
                pkt = Packet(fl.id, MSS, t, fl.seq)
                fl.seq += 1
                buffer.append(pkt)
                buffer_bytes += MSS
                fl.cca.on_sent(MSS)
                inflight_pkts[fl.id] += 1
                send_budget -= MSS

        # Logs every 50ms
        if step % max(1, int(0.05 / cfg.dt_s)) == 0:
            for fl in flows:
                stt = fl.cca.state()
                fl.log.t.append(t)
                fl.log.cwnd.append(stt.cwnd_bytes)
                fl.log.inflight.append(fl.cca.bytes_in_flight)
                fl.log.rtt.append(st.rtt_s)
                fl.log.mode.append(stt.mode)
                # instantaneous goodput over last 50ms window
                dt = 0.05
                gp = fl.bytes_since_mark * 8 / dt
                fl.log.goodput_bps.append(gp)
                fl.bytes_since_mark = 0

    return SimResult(
        handovers=list(path.handover_times),
        flows=[fl.log for fl in flows],
        cfg=cfg,
        cca_names=[fl.cca.name for fl in flows],
        ascent_ingest=ingest_stats,
        orb_samples=orb_samples,
    )
