"""Evaluation metrics for LEO transport experiments."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence
import math
import numpy as np

from leo_cc.sim import FlowLog, SimResult


@dataclass
class FlowMetrics:
    name: str
    goodput_bps: float
    avg_rtt_s: float
    p95_rtt_s: float
    p99_rtt_s: float
    loss_rate: float
    utilization: float
    retrans_proxy: float


def _pct(xs: Sequence[float], p: float) -> float:
    if not xs:
        return float("nan")
    a = np.asarray(xs, dtype=float)
    return float(np.percentile(a, p))


def summarize_flow(name: str, log: FlowLog, duration_s: float, capacity_ref: float) -> FlowMetrics:
    goodput = log.delivered_bytes * 8 / max(duration_s, 1e-9)
    rtts = log.samples_rtt or [0.0]
    lost = log.lost_bytes
    total = log.delivered_bytes + lost
    loss_rate = lost / total if total > 0 else 0.0
    util = goodput / capacity_ref if capacity_ref > 0 else 0.0
    return FlowMetrics(
        name=name,
        goodput_bps=goodput,
        avg_rtt_s=float(np.mean(rtts)),
        p95_rtt_s=_pct(rtts, 95),
        p99_rtt_s=_pct(rtts, 99),
        loss_rate=loss_rate,
        utilization=util,
        retrans_proxy=loss_rate,
    )


def jain_fairness(throughputs: Sequence[float]) -> float:
    xs = np.asarray(throughputs, dtype=float)
    if len(xs) == 0:
        return float("nan")
    s = xs.sum()
    if s <= 0:
        return 0.0
    return float((s * s) / (len(xs) * (xs * xs).sum()))


def summarize_result(res: SimResult) -> list[FlowMetrics]:
    cap_ref = (res.cfg.capacity_min_bps + res.cfg.capacity_max_bps) / 2
    out = []
    for name, fl in zip(res.cca_names, res.flows):
        out.append(summarize_flow(name, fl, res.cfg.duration_s, cap_ref))
    return out
