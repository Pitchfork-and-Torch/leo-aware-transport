#!/usr/bin/env python3
"""v3.15 diagnosis: B/600 recovery-exit vs A/1 (delivery vs cwnd).

Hypothesis (non-binding): B/600 stays in congestive_recovery after the fade
while delivery has already recovered. FastExit would restore cwnd when
delivery ≥ ~0.95 × pre-cut bw_est. Must not tax A/1 or A/600.

Endpoint-only. Era buffer 1 MB. Soft-QIR α frozen 0.20. Crest defaults.
Does not implement the lever — measures whether it would fire, and on whom.

Usage:
  python -m experiments.diag_fastexit --tag 20260814-v315-fastexit --workers 3
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from experiments.run_leocc import LEOCC_BUFFER_BYTES, window_cfg
from experiments.slice_leocc import OUT_DIR
from leo_cc.ccas import BbrCCA, LeoAwareCCA, MSS
from leo_cc.metrics import summarize_result
from leo_cc.sim import run_sim

WINDOWS = {
    "A1": OUT_DIR / "q00_A_downlink_001.csv",
    "A600": OUT_DIR / "q25_A_downlink_600.csv",
    "B600": OUT_DIR / "q50_B_downlink_600.csv",
}

# FastExit would-fire bar (diagnosis only; not a shipped knob).
FE_RATIO = 0.95
# Under-windowed bar: cwnd / delivery-BDP. Used to judge A-tax risk.
UNDER_BDP = 0.70


class ProbeLeo(LeoAwareCCA):
    """Crest + congestive-cut / recovery-exit traces."""

    def __init__(self, **kw):
        super().__init__(**kw)
        self.cuts: list[dict] = []
        self.exits: list[dict] = []
        self.reprobe_events: list[dict] = []
        self.diag_t: list[float] = []
        self.diag_bw: list[float] = []
        self.diag_cwnd: list[float] = []
        self.diag_rate: list[float] = []
        self.diag_mode: list[str] = []
        self.diag_in_rec: list[int] = []
        self.diag_deliv_recovered: list[int] = []
        self.diag_cwnd_ratio: list[float] = []
        self._fe_pre_bw = 0.0
        self._fe_pre_cwnd = 0.0
        self._fe_cut_t = -1.0
        self._fe_in_recovery = False
        self._fe_deliv_ok_t = -1.0
        self._open_cut: dict | None = None
        self.would_fire = 0
        self.would_fire_under = 0  # fire AND cwnd < 0.70 × delivery BDP

    def _enter_reprobe(self, t, reason, **kw):
        self.reprobe_events.append({"t": float(t), "reason": str(reason)})
        super()._enter_reprobe(t, reason, **kw)

    def on_loss(self, t: float, bytes_lost: int, congestive: bool) -> None:
        if congestive and t >= self._orb_mobility_until:
            rate = self._delivery_rate_sample(t)
            if rate <= 0:
                rate = self.rate_ewma
            pre_bw = max(self.bw_est, self.rate_ewma, rate)
            pre_cwnd = self.cwnd
            self._fe_pre_bw = pre_bw
            self._fe_pre_cwnd = pre_cwnd
            self._fe_cut_t = t
            self._fe_in_recovery = True
            self._fe_deliv_ok_t = -1.0
            rec = {
                "t": float(t),
                "pre_cwnd_mss": pre_cwnd / MSS,
                "pre_bw_mbps": pre_bw / 1e6,
                "rate_mbps": rate / 1e6,
                "bw_est_mbps": self.bw_est / 1e6,
                "min_rtt_ms": (self.min_rtt * 1000) if self.min_rtt < 1e17 else -1.0,
            }
            self.cuts.append(rec)
            self._open_cut = rec
        super().on_loss(t, bytes_lost, congestive)

    def on_ack(self, t: float, rtt_s: float, bytes_acked: int, lost: int = 0) -> None:
        super().on_ack(t, rtt_s, bytes_acked, lost)
        rate = self._delivery_rate_sample(t)
        if rate <= 0:
            rate = self.rate_ewma
        recovered = (
            self._fe_in_recovery
            and self._fe_pre_bw > 1e6
            and rate >= FE_RATIO * self._fe_pre_bw
        )
        if recovered and self._fe_deliv_ok_t < 0:
            self._fe_deliv_ok_t = t
        rtt_ref = self.min_rtt if self.min_rtt < 1e17 else max(rtt_s, 0.02)
        deliv_bdp = (rate * rtt_ref / 8.0) if rate > 0 and rtt_ref > 0 else 0.0
        under = deliv_bdp > 0 and self.cwnd < UNDER_BDP * deliv_bdp
        if recovered:
            self.would_fire += 1
            if under:
                self.would_fire_under += 1
            if self._open_cut is not None and "exit_t" not in self._open_cut:
                self._open_cut["exit_t"] = float(t)
                self._open_cut["exit_dt_s"] = float(t - self._fe_cut_t)
                self._open_cut["exit_cwnd_mss"] = self.cwnd / MSS
                self._open_cut["exit_rate_mbps"] = rate / 1e6
                self._open_cut["exit_under"] = bool(under)
                self.exits.append(dict(self._open_cut))
                self._open_cut = None
            # Diagnosis only: do not restore. Stay in measured Crest path.
            self._fe_in_recovery = False
        if not self.diag_t or t - self.diag_t[-1] >= 0.05:
            self.diag_t.append(float(t))
            self.diag_bw.append(self.bw_est / 1e6)
            self.diag_cwnd.append(self.cwnd / MSS)
            self.diag_rate.append(rate / 1e6)
            self.diag_mode.append(self.mode)
            self.diag_in_rec.append(1 if self.mode == "congestive_recovery" else 0)
            self.diag_deliv_recovered.append(1 if recovered else 0)
            self.diag_cwnd_ratio.append(
                (self.cwnd / deliv_bdp) if deliv_bdp > 0 else -1.0
            )


class ProbeBbr(BbrCCA):
    def __init__(self, **kw):
        super().__init__(**kw)
        self.diag_t: list[float] = []
        self.diag_bw: list[float] = []
        self.diag_cwnd: list[float] = []
        self.diag_mode: list[str] = []

    def on_ack(self, t, rtt_s, bytes_acked, lost=0):
        super().on_ack(t, rtt_s, bytes_acked, lost)
        if not self.diag_t or t - self.diag_t[-1] >= 0.05:
            self.diag_t.append(float(t))
            self.diag_bw.append(self.bw_est / 1e6)
            self.diag_cwnd.append(self.cwnd / MSS)
            self.diag_mode.append(self.mode)


def _streaks(flags: list[int]) -> list[int]:
    out: list[int] = []
    n = 0
    for f in flags:
        if f:
            n += 1
        elif n:
            out.append(n)
            n = 0
    if n:
        out.append(n)
    return out


def _job(payload: dict) -> dict:
    window = payload["window"]
    csv = Path(payload["csv"])
    kind = payload["kind"]
    captured: dict = {}

    def factory():
        cca = ProbeBbr() if kind == "bbr" else ProbeLeo()
        captured["cca"] = cca
        return cca

    print(f"diag {window} {kind} ...", flush=True)
    cfg = window_cfg(csv, buffer_bytes=LEOCC_BUFFER_BYTES)
    res = run_sim(factory, cfg=cfg, n_flows=1, path_hint_mode="none")
    cca = captured["cca"]
    m = summarize_result(res)[0]
    modes = Counter(res.flows[0].mode)
    out: dict = {
        "window": window,
        "variant": "BBRv3approx" if kind == "bbr" else "Crest",
        "goodput_mbps": m.goodput_bps / 1e6,
        "p95_rtt_ms": m.p95_rtt_s * 1000,
        "mode_hist": dict(modes),
        "mean_cwnd_mss": float(np.mean(res.flows[0].cwnd) / MSS),
        "frac_cong_rec": float(
            np.mean([str(md) == "congestive_recovery" for md in res.flows[0].mode])
        ),
    }
    if isinstance(cca, ProbeLeo):
        reasons = Counter(e["reason"] for e in cca.reprobe_events)
        exit_dts = [e["exit_dt_s"] for e in cca.exits if "exit_dt_s" in e]
        under_frac = (
            float(np.mean([e.get("exit_under", False) for e in cca.exits]))
            if cca.exits
            else 0.0
        )
        ratios = [r for r in cca.diag_cwnd_ratio if r > 0]
        rec_ratios = [
            r
            for r, rec in zip(cca.diag_cwnd_ratio, cca.diag_in_rec)
            if rec and r > 0
        ]
        streaks = _streaks(cca.diag_in_rec)
        out.update(
            {
                "reconfigs_detected": cca.reconfigs_detected,
                "reprobe_reasons": dict(reasons),
                "ser_lite_count": cca.ser_lite_count,
                "ca_aborts": cca.ca_aborts,
                "n_cong_cuts": len(cca.cuts),
                "n_deliv_exits": len(cca.exits),
                "would_fire_acks": cca.would_fire,
                "would_fire_under_acks": cca.would_fire_under,
                "frac_exits_under_bdp": under_frac,
                "mean_exit_dt_s": float(np.mean(exit_dts)) if exit_dts else -1.0,
                "p50_exit_dt_s": float(np.median(exit_dts)) if exit_dts else -1.0,
                "p95_exit_dt_s": (
                    float(np.percentile(exit_dts, 95)) if exit_dts else -1.0
                ),
                "mean_bw_mbps": float(np.mean(cca.diag_bw)) if cca.diag_bw else 0.0,
                "mean_rate_mbps": float(np.mean(cca.diag_rate)) if cca.diag_rate else 0.0,
                "mean_cwnd_over_deliv_bdp": float(np.mean(ratios)) if ratios else -1.0,
                "mean_cwnd_over_deliv_bdp_in_rec": (
                    float(np.mean(rec_ratios)) if rec_ratios else -1.0
                ),
                "n_rec_streaks": len(streaks),
                "mean_rec_streak_samples": float(np.mean(streaks)) if streaks else 0.0,
                "max_rec_streak_samples": int(max(streaks)) if streaks else 0,
                "frac_samples_deliv_recovered": (
                    float(np.mean(cca.diag_deliv_recovered))
                    if cca.diag_deliv_recovered
                    else 0.0
                ),
                "mean_min_rtt_ms": (
                    float(np.mean([x for x in [
                        (cca.min_rtt * 1000) if cca.min_rtt < 1e17 else -1.0
                    ] if x > 0]))
                    if cca.min_rtt < 1e17
                    else -1.0
                ),
            }
        )
        # min_rtt from last sample is a point; prefer diag if we had stored it.
        # Recompute from cuts for a stable window mean.
        cut_rtts = [c["min_rtt_ms"] for c in cca.cuts if c["min_rtt_ms"] > 0]
        if cut_rtts:
            out["mean_min_rtt_ms"] = float(np.mean(cut_rtts))
    else:
        out.update(
            {
                "mean_bw_mbps": float(np.mean(cca.diag_bw)) if cca.diag_bw else 0.0,
            }
        )
    print(
        f"done {window} {out['variant']}  gp={out['goodput_mbps']:.2f}  "
        f"cong={out['frac_cong_rec']:.2f}  cuts={out.get('n_cong_cuts', '-')}",
        flush=True,
    )
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--tag", default="20260814-v315-fastexit")
    ap.add_argument("--workers", type=int, default=3)
    args = ap.parse_args()
    out_dir = ROOT / "results" / "archive" / args.tag / "diag"
    out_dir.mkdir(parents=True, exist_ok=True)

    jobs = []
    for win, path in WINDOWS.items():
        jobs.append({"window": win, "csv": str(path), "kind": "leo"})
    jobs.append({"window": "B600", "csv": str(WINDOWS["B600"]), "kind": "bbr"})
    jobs.append({"window": "A1", "csv": str(WINDOWS["A1"]), "kind": "bbr"})

    rows: list[dict] = []
    if args.workers <= 1:
        rows = [_job(j) for j in jobs]
    else:
        with ProcessPoolExecutor(max_workers=args.workers) as pool:
            futs = [pool.submit(_job, j) for j in jobs]
            for fut in as_completed(futs):
                rows.append(fut.result())

    (out_dir / "recovery_exit.json").write_text(
        json.dumps(rows, indent=2) + "\n", encoding="utf-8"
    )
    print("\n=== recovery-exit (Crest vs BBR) ===")
    for r in sorted(rows, key=lambda x: (x["window"], x["variant"])):
        extra = ""
        if "n_cong_cuts" in r:
            extra = (
                f"  cuts={r['n_cong_cuts']}"
                f"  deliv_exits={r['n_deliv_exits']}"
                f"  would_fire={r['would_fire_acks']}"
                f"  under={r['would_fire_under_acks']}"
                f"  exit_dt_p50={r['p50_exit_dt_s']:.3f}"
                f"  cwnd/bdp_rec={r['mean_cwnd_over_deliv_bdp_in_rec']:.2f}"
                f"  reasons={r.get('reprobe_reasons')}"
            )
        print(
            f"{r['window']:5s} {r['variant']:12s}  gp={r['goodput_mbps']:7.2f}  "
            f"p95={r['p95_rtt_ms']:6.1f}  cong={r['frac_cong_rec']:.2f}  "
            f"cwnd={r['mean_cwnd_mss']:.0f}mss{extra}"
        )
    print(f"Wrote {out_dir}")


if __name__ == "__main__":
    main()
