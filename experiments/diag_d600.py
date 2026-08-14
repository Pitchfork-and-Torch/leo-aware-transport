#!/usr/bin/env python3
"""v3.14 D/600 diagnosis: why Crest leaves ~150 Mbps vs BBR on the far-site tail.

Endpoint-only. Era buffer 1 MB. Soft-QIR α frozen 0.20. Does not change Crest
defaults. Writes JSON + CSV under results/archive/<tag>/diag/.

Usage:
  python -m experiments.diag_d600 --tag 20260814-v314-d600 --workers 4
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from experiments.run_leocc import LEOCC_BUFFER_BYTES, SIM_DT_S, window_cfg
from experiments.slice_leocc import OUT_DIR
from leo_cc.ccas import BbrCCA, LeoAwareCCA, MSS
from leo_cc.metrics import summarize_result
from leo_cc.network import load_trace_csv
from leo_cc.sim import run_sim

D600 = OUT_DIR / "q100_D_downlink_600.csv"


class ProbeLeo(LeoAwareCCA):
    """Crest with REPROBE / CA / LSG / anticipator / TBPR event logs."""

    def __init__(self, **kw):
        super().__init__(**kw)
        self.reprobe_events: list[dict] = []
        self.ca_events: list[dict] = []
        self.lsg_events: list[dict] = []
        self.tbpr_aborts: int = 0
        self.diag_t: list[float] = []
        self.diag_bw: list[float] = []
        self.diag_cwnd: list[float] = []
        self.diag_min_rtt: list[float] = []
        self.diag_delay_ratio: list[float] = []
        self.diag_mode: list[str] = []

    def _enter_reprobe(self, t, reason, **kw):
        self.reprobe_events.append(
            {
                "t": float(t),
                "reason": str(reason),
                "cwnd_mss": self.cwnd / MSS,
                "bw_mbps": self.bw_est / 1e6,
                "min_rtt_ms": (self.min_rtt * 1000) if self.min_rtt < 1e17 else -1.0,
                "prior_bw_mbps": self.prior_bw / 1e6,
            }
        )
        super()._enter_reprobe(t, reason, **kw)

    def _apply_crest_abort(self, t, bdp):
        before = self.cwnd
        super()._apply_crest_abort(t, bdp)
        if self.cwnd < before * 0.99:
            self.ca_events.append(
                {
                    "t": float(t),
                    "cwnd_before_mss": before / MSS,
                    "cwnd_after_mss": self.cwnd / MSS,
                    "bdp_mss": bdp / MSS,
                }
            )

    def _lsg_surplus_ok(self, t, delay_ratio):
        ok = super()._lsg_surplus_ok(t, delay_ratio)
        if not ok:
            rate = self.rate_ewma if self.rate_ewma > 0 else 0.0
            self.lsg_events.append(
                {
                    "t": float(t),
                    "delay_ratio": float(delay_ratio),
                    "rate_mbps": rate / 1e6,
                    "prior_bw_mbps": self.prior_bw / 1e6,
                }
            )
        return ok

    def on_ack(self, t, rtt_s, bytes_acked, lost=0):
        super().on_ack(t, rtt_s, bytes_acked, lost)
        if not self.diag_t or t - self.diag_t[-1] >= 0.05:
            dr = (
                rtt_s / self.min_rtt
                if self.min_rtt < 1e17 and self.min_rtt > 0
                else 1.0
            )
            self.diag_t.append(float(t))
            self.diag_bw.append(self.bw_est / 1e6)
            self.diag_cwnd.append(self.cwnd / MSS)
            self.diag_min_rtt.append(
                self.min_rtt * 1000 if self.min_rtt < 1e17 else -1.0
            )
            self.diag_delay_ratio.append(float(dr))
            self.diag_mode.append(self.mode)


class ProbeBbr(BbrCCA):
    def __init__(self, **kw):
        super().__init__(**kw)
        self.diag_t: list[float] = []
        self.diag_bw: list[float] = []
        self.diag_cwnd: list[float] = []
        self.diag_min_rtt: list[float] = []
        self.diag_mode: list[str] = []

    def on_ack(self, t, rtt_s, bytes_acked, lost=0):
        super().on_ack(t, rtt_s, bytes_acked, lost)
        if not self.diag_t or t - self.diag_t[-1] >= 0.05:
            self.diag_t.append(float(t))
            self.diag_bw.append(self.bw_est / 1e6)
            self.diag_cwnd.append(self.cwnd / MSS)
            self.diag_min_rtt.append(
                self.min_rtt * 1000 if self.min_rtt < 1e17 else -1.0
            )
            self.diag_mode.append(self.mode)


VARIANTS: dict[str, dict] = {
    "BBRv3approx": {"kind": "bbr"},
    "Crest": {
        "kind": "leo",
        "use_ca": True,
        "use_dlc": True,
        "use_lsg": True,
        "use_anticipator": True,
    },
    "Crest_noCA": {
        "kind": "leo",
        "use_ca": False,
        "use_dlc": True,
        "use_lsg": True,
        "use_anticipator": True,
    },
    "Crest_noLSG": {
        "kind": "leo",
        "use_ca": True,
        "use_dlc": True,
        "use_lsg": False,
        "use_anticipator": True,
    },
    "Crest_noAnt": {
        "kind": "leo",
        "use_ca": True,
        "use_dlc": True,
        "use_lsg": True,
        "use_anticipator": False,
    },
    "v37_oce": {
        "kind": "leo",
        "use_ca": False,
        "use_dlc": False,
        "use_lsg": False,
        "use_anticipator": False,
    },
}


def path_geometry(csv_path: Path) -> dict:
    rows = load_trace_csv(csv_path)
    rtts = np.array([r.rtt_s for r in rows], dtype=float)
    caps = np.array([r.capacity_bps / 1e6 for r in rows], dtype=float)
    d_rtt = np.diff(rtts)
    # Crest classic_jump: rtt > 1.55*med AND jump > 12 ms (rolling 48-sample med)
    classic = 0
    mad_like = 0
    win = 48
    for i in range(win, len(rtts)):
        base = rtts[i - win : i]
        med = float(np.median(base))
        mad = float(np.median(np.abs(base - med)))
        mad = max(mad, 0.002)
        z = (rtts[i] - med) / (1.4826 * mad)
        if rtts[i] > med * 1.55 and rtts[i] - med > 0.012:
            classic += 1
        if z > 3.5 and rtts[i] - med > 0.010:
            mad_like += 1
    return {
        "n": int(len(rows)),
        "rtt_min_ms": float(rtts.min() * 1000),
        "rtt_p50_ms": float(np.percentile(rtts, 50) * 1000),
        "rtt_p95_ms": float(np.percentile(rtts, 95) * 1000),
        "rtt_max_ms": float(rtts.max() * 1000),
        "rtt_jump_p95_ms": float(np.percentile(np.abs(d_rtt), 95) * 1000),
        "rtt_jump_max_ms": float(np.abs(d_rtt).max() * 1000),
        "cap_min_mbps": float(caps.min()),
        "cap_p50_mbps": float(np.percentile(caps, 50)),
        "cap_p82_mbps": float(np.percentile(caps, 82)),
        "cap_p95_mbps": float(np.percentile(caps, 95)),
        "cap_max_mbps": float(caps.max()),
        "cap_mean_mbps": float(caps.mean()),
        "classic_jump_slots": classic,
        "rtt_mad_like_slots": mad_like,
        "frac_rtt_gt_1_35_p50": float((rtts > 1.35 * np.median(rtts)).mean()),
        "frac_rtt_gt_1_18_min": float((rtts > 1.18 * rtts.min()).mean()),
        "frac_rtt_gt_1_35_min": float((rtts > 1.35 * rtts.min()).mean()),
    }


def _job(name: str) -> dict:
    spec = VARIANTS[name]
    captured: dict = {}

    def factory():
        if spec["kind"] == "bbr":
            cca = ProbeBbr()
        else:
            flags = {
                k: spec[k]
                for k in ("use_ca", "use_dlc", "use_lsg", "use_anticipator")
            }
            cca = ProbeLeo(**flags)
        captured["cca"] = cca
        return cca

    print(f"diag D/600 {name} ...", flush=True)
    cfg = window_cfg(D600, buffer_bytes=LEOCC_BUFFER_BYTES)
    res = run_sim(factory, cfg=cfg, n_flows=1, path_hint_mode="none")
    cca = captured["cca"]
    m = summarize_result(res)[0]
    modes = Counter(res.flows[0].mode)
    out: dict = {
        "variant": name,
        "goodput_mbps": m.goodput_bps / 1e6,
        "p95_rtt_ms": m.p95_rtt_s * 1000,
        "p95_path_rtt_ms": m.p95_path_rtt_s * 1000,
        "p95_excess_rtt_ms": m.p95_excess_rtt_s * 1000,
        "mean_excess_rtt_ms": m.mean_excess_rtt_s * 1000,
        "mode_hist": dict(modes),
        "mean_cwnd_mss": float(np.mean(res.flows[0].cwnd) / MSS),
        "p50_cwnd_mss": float(np.median(res.flows[0].cwnd) / MSS),
    }
    if isinstance(cca, ProbeLeo):
        reasons = Counter(e["reason"] for e in cca.reprobe_events)
        out.update(
            {
                "reconfigs_detected": cca.reconfigs_detected,
                "reprobe_reasons": dict(reasons),
                "reprobe_events": cca.reprobe_events[:40],
                "n_reprobe_events": len(cca.reprobe_events),
                "ca_aborts": cca.ca_aborts,
                "n_ca_events": len(cca.ca_events),
                "lsg_clamps": cca.lsg_clamps,
                "n_lsg_events": len(cca.lsg_events),
                "anticipator_holds": cca.anticipator_holds,
                "keel_rollbacks": cca.keel_rollbacks,
                "oce_echos": cca.oce_echos,
                "ser_lite_count": cca.ser_lite_count,
                "mean_bw_mbps": float(np.mean(cca.diag_bw)) if cca.diag_bw else 0.0,
                "p50_bw_mbps": float(np.median(cca.diag_bw)) if cca.diag_bw else 0.0,
                "p95_bw_mbps": (
                    float(np.percentile(cca.diag_bw, 95)) if cca.diag_bw else 0.0
                ),
                "mean_min_rtt_ms": (
                    float(np.mean([x for x in cca.diag_min_rtt if x > 0]))
                    if cca.diag_min_rtt
                    else -1.0
                ),
                "mean_delay_ratio": (
                    float(np.mean(cca.diag_delay_ratio)) if cca.diag_delay_ratio else 1.0
                ),
                "frac_delay_ratio_gt_118": (
                    float(np.mean([d > 1.18 for d in cca.diag_delay_ratio]))
                    if cca.diag_delay_ratio
                    else 0.0
                ),
                "frac_delay_ratio_gt_135": (
                    float(np.mean([d > 1.35 for d in cca.diag_delay_ratio]))
                    if cca.diag_delay_ratio
                    else 0.0
                ),
                "frac_reprobe_mode": float(
                    np.mean(
                        [
                            str(md).startswith("reprobe") or str(md).startswith("ser")
                            for md in res.flows[0].mode
                        ]
                    )
                ),
            }
        )
    else:
        out.update(
            {
                "mean_bw_mbps": float(np.mean(cca.diag_bw)) if cca.diag_bw else 0.0,
                "p50_bw_mbps": float(np.median(cca.diag_bw)) if cca.diag_bw else 0.0,
                "p95_bw_mbps": (
                    float(np.percentile(cca.diag_bw, 95)) if cca.diag_bw else 0.0
                ),
                "mean_min_rtt_ms": (
                    float(np.mean([x for x in cca.diag_min_rtt if x > 0]))
                    if cca.diag_min_rtt
                    else -1.0
                ),
            }
        )
    print(
        f"done D/600 {name}  gp={out['goodput_mbps']:.2f}  "
        f"p95={out['p95_rtt_ms']:.1f}  bw~{out['mean_bw_mbps']:.1f}",
        flush=True,
    )
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--tag", default="20260814-v314-d600")
    ap.add_argument("--workers", type=int, default=4)
    args = ap.parse_args()
    if not D600.is_file():
        raise SystemExit(f"missing {D600}")
    out_dir = ROOT / "results" / "archive" / args.tag / "diag"
    out_dir.mkdir(parents=True, exist_ok=True)

    geo = path_geometry(D600)
    (out_dir / "d600_path.json").write_text(
        json.dumps(geo, indent=2) + "\n", encoding="utf-8"
    )
    print("=== D/600 path ===")
    print(json.dumps(geo, indent=2))

    names = list(VARIANTS)
    rows: list[dict] = []
    if args.workers <= 1:
        rows = [_job(n) for n in names]
    else:
        with ProcessPoolExecutor(max_workers=args.workers) as pool:
            futs = {pool.submit(_job, n): n for n in names}
            for fut in as_completed(futs):
                rows.append(fut.result())
    rows.sort(key=lambda r: names.index(r["variant"]))
    slim = []
    for r in rows:
        slim.append({k: v for k, v in r.items() if k != "reprobe_events"})
    (out_dir / "d600_variants.json").write_text(
        json.dumps(rows, indent=2) + "\n", encoding="utf-8"
    )
    pd.DataFrame(slim).to_csv(out_dir / "d600_variants.csv", index=False)
    print("\n=== D/600 variants ===")
    for r in rows:
        extra = ""
        if "reconfigs_detected" in r:
            extra = (
                f"  reprobes={r['reconfigs_detected']}"
                f"  ca={r['ca_aborts']}"
                f"  lsg={r['lsg_clamps']}"
                f"  ant={r['anticipator_holds']}"
                f"  reasons={r.get('reprobe_reasons')}"
            )
        print(
            f"{r['variant']:14s}  gp={r['goodput_mbps']:7.2f}  "
            f"p95={r['p95_rtt_ms']:6.1f}  bw={r['mean_bw_mbps']:7.1f}  "
            f"cwnd={r['mean_cwnd_mss']:7.1f}mss{extra}"
        )
    print(f"Wrote {out_dir}")


if __name__ == "__main__":
    main()
