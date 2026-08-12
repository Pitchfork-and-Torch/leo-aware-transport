"""Matplotlib visualizations for LEO CC experiments."""
from __future__ import annotations

from pathlib import Path
from typing import Optional
import matplotlib.pyplot as plt
import numpy as np

from leo_cc.sim import SimResult


def plot_timeseries(res: SimResult, out: Path, title: str = "") -> Path:
    out = Path(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    n = len(res.flows)
    fig, axes = plt.subplots(3, 1, figsize=(10, 8), sharex=True)
    for i, (log, name) in enumerate(zip(res.flows, res.cca_names)):
        t = np.asarray(log.t)
        axes[0].plot(t, np.asarray(log.cwnd) / 1200.0, label=f"{name} cwnd(MSS)")
        axes[1].plot(t, np.asarray(log.goodput_bps) / 1e6, label=f"{name} goodput Mbps")
        axes[2].plot(t, np.asarray(log.rtt) * 1000.0, label=f"{name} RTT ms", alpha=0.8)
    for ax in axes:
        for h in res.handovers:
            ax.axvline(h, color="orange", alpha=0.35, linewidth=1)
    axes[0].set_ylabel("cwnd (MSS)")
    axes[1].set_ylabel("goodput (Mbps)")
    axes[2].set_ylabel("path RTT (ms)")
    axes[2].set_xlabel("time (s)")
    axes[0].legend(loc="upper right", fontsize=8)
    axes[1].legend(loc="upper right", fontsize=8)
    fig.suptitle(title or "LEO transport timeseries (orange = handover)")
    fig.tight_layout()
    fig.savefig(out, dpi=140)
    plt.close(fig)
    return out


def plot_throughput_latency(rows: list[dict], out: Path, title: str = "") -> Path:
    out = Path(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    fig, ax = plt.subplots(figsize=(6, 5))
    for r in rows:
        ax.scatter(
            r["p95_rtt_ms"],
            r["goodput_mbps"],
            s=80,
            label=r["name"],
        )
        ax.annotate(r["name"], (r["p95_rtt_ms"], r["goodput_mbps"]), fontsize=8)
    ax.set_xlabel("p95 RTT (ms)")
    ax.set_ylabel("Goodput (Mbps)")
    ax.set_title(title or "Throughput-latency tradeoff")
    ax.grid(True, alpha=0.3)
    fig.tight_layout()
    fig.savefig(out, dpi=140)
    plt.close(fig)
    return out
