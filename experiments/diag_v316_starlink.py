#!/usr/bin/env python3
"""v3.16 diagnosis: why Crest is ~0.37 Mbps behind BBR on starlink_v1.

Same rails as the v3.9 lock: leo_fast_ho 90s, seeds 13,7,42,99,123,
synthetic starlink_v1, soft-QIR α=0.20, endpoint-only.

Does not change CCA defaults. Measures pace-bind, underfill, REPROBE time,
bw_est vs BBR max-filter, and first-2s starve (WetLinks SH leftover — verify
here; do not import that knob).

Usage:
  python -m experiments.diag_v316_starlink
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from leo_cc.ccas import BbrCCA, LeoAwareCCA, MSS
from leo_cc.harness import PRODUCT_PATH_PROFILE, PRODUCT_SEEDS, apply_profile
from leo_cc.metrics import summarize_result
from leo_cc.network import LeoPath, LeoPathConfig, walk_path_geometry
from leo_cc.sim import SOFT_QIR_ALPHA, run_sim

OUT = ROOT / "results" / "archive" / "20260814-v316-starlink" / "diag"


class DiagCrest(LeoAwareCCA):
    """Count pace vs cwnd binds and clean-underfill slots. No control change."""

    def __init__(self, **kw):
        super().__init__(**kw)
        self.diag_slots = 0
        self.diag_pace_bind = 0
        self.diag_cwnd_bind = 0
        self.diag_clean_underfill = 0
        self.diag_first2_pace_bind = 0
        self.diag_first2_slots = 0
        self.diag_reprobe_acks = 0
        self.diag_acks = 0
        self.diag_bw_sum = 0.0
        self.diag_bw_n = 0
        self.diag_util_num = 0.0
        self.diag_util_den = 0.0

    def on_ack(self, t: float, rtt_s: float, bytes_acked: int, lost: int = 0) -> None:
        super().on_ack(t, rtt_s, bytes_acked, lost)
        self.diag_acks += 1
        if t < self.reprobe_until:
            self.diag_reprobe_acks += 1
        if self.bw_est > 0:
            self.diag_bw_sum += self.bw_est
            self.diag_bw_n += 1

    def can_send(self, t: float) -> int:
        room_cwnd = max(0.0, self.cwnd - self.bytes_in_flight)
        result = super().can_send(t)
        self.diag_slots += 1
        if t < 2.0:
            self.diag_first2_slots += 1
        if room_cwnd >= MSS and result + 0.5 < room_cwnd:
            self.diag_pace_bind += 1
            if t < 2.0:
                self.diag_first2_pace_bind += 1
        elif room_cwnd < MSS:
            self.diag_cwnd_bind += 1
        delay = (
            (self.rtt_hist[-1] / self.min_rtt)
            if self.rtt_hist and self.min_rtt < 1e17 and self.min_rtt > 0
            else 1.0
        )
        bdp = (
            self.bw_est * (self.min_rtt if self.min_rtt < 1e17 else 0.04) / 8.0
            if self.bw_est > 0
            else 0.0
        )
        if (
            bdp > 0
            and self.bytes_in_flight < 0.85 * bdp
            and delay < 1.14
            and t >= self.reprobe_until
        ):
            self.diag_clean_underfill += 1
        return result


class DiagBbr(BbrCCA):
    def __init__(self, **kw):
        super().__init__(**kw)
        self.diag_bw_sum = 0.0
        self.diag_bw_n = 0
        self.diag_acks = 0

    def on_ack(self, t: float, rtt_s: float, bytes_acked: int, lost: int = 0) -> None:
        super().on_ack(t, rtt_s, bytes_acked, lost)
        self.diag_acks += 1
        if self.bw_est > 0:
            self.diag_bw_sum += self.bw_est
            self.diag_bw_n += 1


def _cfg(seed: int) -> LeoPathConfig:
    return apply_profile(
        LeoPathConfig(
            duration_s=90,
            handover_interval_s=12,
            handover_jitter_s=4,
            seed=seed,
        ),
        PRODUCT_PATH_PROFILE,
    )


def _mode_frac(modes: list[str], pred) -> float:
    if not modes:
        return 0.0
    return sum(1 for m in modes if pred(m)) / len(modes)


def _mean(xs: list[float]) -> float:
    return sum(xs) / len(xs) if xs else float("nan")


def run_seed(seed: int) -> dict:
    cfg = _cfg(seed)
    geom = walk_path_geometry(cfg)
    path = LeoPath(cfg)
    caps = []
    while path.t < cfg.duration_s:
        st = path.step()
        caps.append(st.capacity_bps)

    crest_box = {}
    bbr_box = {}

    def crest_factory():
        c = DiagCrest()
        crest_box["cca"] = c
        return c

    def bbr_factory():
        c = DiagBbr()
        bbr_box["cca"] = c
        return c

    cres = run_sim(crest_factory, cfg=_cfg(seed), n_flows=1)
    bres = run_sim(bbr_factory, cfg=_cfg(seed), n_flows=1)
    cm = summarize_result(cres)[0]
    bm = summarize_result(bres)[0]
    cc = crest_box["cca"]
    bc = bbr_box["cca"]
    clog = cres.flows[0]
    blog = bres.flows[0]

    def util(log, n=None):
        n = n or min(len(log.goodput_bps), len(caps))
        # logs every 50ms; caps every dt (0.01). downsample caps.
        step = max(1, int(0.05 / cfg.dt_s))
        nums = []
        for i, gp in enumerate(log.goodput_bps):
            idx = min(i * step, len(caps) - 1)
            if caps[idx] > 0:
                nums.append(gp / caps[idx])
        return _mean(nums)

    def first2_gp(log):
        # first 2s of 50ms marks → 40 samples
        xs = log.goodput_bps[:40]
        return _mean(xs) / 1e6 if xs else float("nan")

    row = {
        "seed": seed,
        "oracle_gp": geom["oracle_gp_mbps"],
        "path_p95": geom["path_p95_ms"],
        "crest_gp": cm.goodput_bps / 1e6,
        "bbr_gp": bm.goodput_bps / 1e6,
        "delta_gp": (cm.goodput_bps - bm.goodput_bps) / 1e6,
        "crest_p95": cm.p95_rtt_s * 1000,
        "bbr_p95": bm.p95_rtt_s * 1000,
        "crest_loss": cm.loss_rate,
        "bbr_loss": bm.loss_rate,
        "crest_mean_excess_ms": cm.mean_excess_rtt_s * 1000,
        "bbr_mean_excess_ms": bm.mean_excess_rtt_s * 1000,
        "crest_bw_est_mbps": (cc.diag_bw_sum / cc.diag_bw_n / 1e6) if cc.diag_bw_n else 0.0,
        "bbr_bw_est_mbps": (bc.diag_bw_sum / bc.diag_bw_n / 1e6) if bc.diag_bw_n else 0.0,
        "pace_bind_frac": cc.diag_pace_bind / max(1, cc.diag_slots),
        "cwnd_bind_frac": cc.diag_cwnd_bind / max(1, cc.diag_slots),
        "clean_underfill_frac": cc.diag_clean_underfill / max(1, cc.diag_slots),
        "first2_pace_bind_frac": cc.diag_first2_pace_bind / max(1, cc.diag_first2_slots),
        "reprobe_ack_frac": cc.diag_reprobe_acks / max(1, cc.diag_acks),
        "reconfigs": cc.reconfigs_detected,
        "ca_aborts": cc.ca_aborts,
        "lsg_clamps": cc.lsg_clamps,
        "anticipator_holds": cc.anticipator_holds,
        "crest_util": util(clog),
        "bbr_util": util(blog),
        "crest_first2_gp": first2_gp(clog),
        "bbr_first2_gp": first2_gp(blog),
        "crest_reprobe_mode_frac": _mode_frac(
            clog.mode, lambda m: "reprobe" in m or str(m).startswith("ser")
        ),
        "crest_yield_mode_frac": _mode_frac(clog.mode, lambda m: "yield" in m or m == "ca_abort"),
        "mean_cwnd_crest": _mean(clog.cwnd),
        "mean_cwnd_bbr": _mean(blog.cwnd),
        "mean_inflight_crest": _mean(clog.inflight),
        "mean_inflight_bbr": _mean(blog.inflight),
    }
    return row


def main() -> None:
    assert PRODUCT_PATH_PROFILE == "starlink_v1"
    assert SOFT_QIR_ALPHA == 0.20
    OUT.mkdir(parents=True, exist_ok=True)
    rows = []
    print(
        f"diag v3.16 starlink_v1 seeds={PRODUCT_SEEDS} α={SOFT_QIR_ALPHA}",
        flush=True,
    )
    for seed in PRODUCT_SEEDS:
        print(f"seed {seed} ...", flush=True)
        row = run_seed(seed)
        rows.append(row)
        print(
            f"  Crest {row['crest_gp']:.2f} vs BBR {row['bbr_gp']:.2f} "
            f"Δ={row['delta_gp']:+.2f}  pace_bind={row['pace_bind_frac']:.3f} "
            f"underfill={row['clean_underfill_frac']:.3f} "
            f"bw {row['crest_bw_est_mbps']:.1f}/{row['bbr_bw_est_mbps']:.1f} "
            f"first2 {row['crest_first2_gp']:.1f}/{row['bbr_first2_gp']:.1f}",
            flush=True,
        )

    means = {k: _mean([r[k] for r in rows]) for k in rows[0] if k != "seed"}
    payload = {
        "era": "starlink_v1",
        "synthetic": True,
        "soft_qir_alpha": SOFT_QIR_ALPHA,
        "seeds": list(PRODUCT_SEEDS),
        "per_seed": rows,
        "means": means,
        "hypotheses": {
            "H1_pace_bind": (
                "Crest soft-pacing binds can_send below cwnd on a material "
                "fraction of slots; BBR has no pace bind."
            ),
            "H2_startup_starve": (
                "First 2s Crest goodput lags BBR (1.28×/p82/1.08× pace vs "
                "BBR 2×/max-filter/no pace). Isolated from WetLinks SH bundle."
            ),
            "H3_bw_est_low": (
                "Crest p82 bw_est sits below BBR max-filter; CCH already "
                "rejected raising the filter on this path."
            ),
            "H4_reprobe_tax": (
                "REPROBE/SER time plus LSG clamps leave post-hop underfill "
                "vs BBR loss-ignore."
            ),
        },
    }
    (OUT / "diagnosis.json").write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print("\n=== means ===")
    for k, v in means.items():
        print(f"  {k:28s} {v:.4f}")
    print(f"\nwrote {OUT / 'diagnosis.json'}")


if __name__ == "__main__":
    main()
