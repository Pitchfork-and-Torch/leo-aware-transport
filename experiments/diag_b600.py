#!/usr/bin/env python3
"""v3.14 follow-up: B/600 diagnosis (same rails as D/600).

Endpoint-only. Era buffer 1 MB. Soft-QIR α frozen 0.20.
Also dumps Crest-default counters on A/1 and A/600 so a fade-hold
generalization can be checked against “A must stay unchanged.”

Usage:
  python -m experiments.diag_b600 --tag 20260814-v314-b600 --workers 4
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

from experiments.diag_d600 import (
    VARIANTS,
    ProbeBbr,
    ProbeLeo,
    path_geometry,
)
from experiments.run_leocc import LEOCC_BUFFER_BYTES, window_cfg
from experiments.slice_leocc import OUT_DIR
from leo_cc.ccas import LeoAwareCCA, MSS
from leo_cc.metrics import summarize_result
from leo_cc.sim import run_sim

WINDOWS = {
    "A1": OUT_DIR / "q00_A_downlink_001.csv",
    "A600": OUT_DIR / "q25_A_downlink_600.csv",
    "B600": OUT_DIR / "q50_B_downlink_600.csv",
}


def _summarize(name: str, window: str, csv: Path, spec: dict) -> dict:
    captured: dict = {}

    def factory():
        if spec.get("kind") == "bbr":
            cca = ProbeBbr()
        elif spec.get("kind") == "farhold":
            cca = ProbeLeo(
                use_ca=True,
                use_dlc=True,
                use_lsg=True,
                use_anticipator=True,
                use_far_hold=True,
            )
        else:
            flags = {
                k: spec[k]
                for k in ("use_ca", "use_dlc", "use_lsg", "use_anticipator")
            }
            cca = ProbeLeo(**flags)
        captured["cca"] = cca
        return cca

    print(f"diag {window} {name} ...", flush=True)
    cfg = window_cfg(csv, buffer_bytes=LEOCC_BUFFER_BYTES)
    res = run_sim(factory, cfg=cfg, n_flows=1, path_hint_mode="none")
    cca = captured["cca"]
    m = summarize_result(res)[0]
    modes = Counter(res.flows[0].mode)
    out: dict = {
        "window": window,
        "variant": name,
        "goodput_mbps": m.goodput_bps / 1e6,
        "p95_rtt_ms": m.p95_rtt_s * 1000,
        "mode_hist": dict(modes),
        "mean_cwnd_mss": float(np.mean(res.flows[0].cwnd) / MSS),
    }
    if isinstance(cca, ProbeLeo):
        reasons = Counter(e["reason"] for e in cca.reprobe_events)
        out.update(
            {
                "reconfigs_detected": cca.reconfigs_detected,
                "reprobe_reasons": dict(reasons),
                "n_reprobe_events": len(cca.reprobe_events),
                "ca_aborts": cca.ca_aborts,
                "lsg_clamps": cca.lsg_clamps,
                "anticipator_holds": cca.anticipator_holds,
                "ser_lite_count": cca.ser_lite_count,
                "far_holds": getattr(cca, "far_holds", 0),
                "mean_bw_mbps": float(np.mean(cca.diag_bw)) if cca.diag_bw else 0.0,
                "mean_min_rtt_ms": (
                    float(np.mean([x for x in cca.diag_min_rtt if x > 0]))
                    if cca.diag_min_rtt
                    else -1.0
                ),
                "frac_reprobe_mode": float(
                    np.mean(
                        [
                            str(md).startswith("reprobe") or str(md).startswith("ser")
                            for md in res.flows[0].mode
                        ]
                    )
                ),
                "frac_cong_rec": float(
                    np.mean([str(md) == "congestive_recovery" for md in res.flows[0].mode])
                ),
            }
        )
    else:
        out.update(
            {
                "mean_bw_mbps": float(np.mean(cca.diag_bw)) if cca.diag_bw else 0.0,
                "mean_min_rtt_ms": (
                    float(np.mean([x for x in cca.diag_min_rtt if x > 0]))
                    if cca.diag_min_rtt
                    else -1.0
                ),
            }
        )
    print(
        f"done {window} {name}  gp={out['goodput_mbps']:.2f}  "
        f"p95={out['p95_rtt_ms']:.1f}  bw~{out.get('mean_bw_mbps', 0):.1f}",
        flush=True,
    )
    return out


def _job(payload: dict) -> dict:
    return _summarize(
        payload["name"],
        payload["window"],
        Path(payload["csv"]),
        payload["spec"],
    )


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--tag", default="20260814-v314-b600")
    ap.add_argument("--workers", type=int, default=4)
    args = ap.parse_args()
    out_dir = ROOT / "results" / "archive" / args.tag / "diag"
    out_dir.mkdir(parents=True, exist_ok=True)

    geo = path_geometry(WINDOWS["B600"])
    (out_dir / "b600_path.json").write_text(
        json.dumps(geo, indent=2) + "\n", encoding="utf-8"
    )
    print("=== B/600 path ===")
    print(json.dumps(geo, indent=2))

    jobs = []
    for name, spec in VARIANTS.items():
        jobs.append(
            {
                "name": name,
                "window": "B600",
                "csv": str(WINDOWS["B600"]),
                "spec": spec,
            }
        )
    # Forced FarHold on B (current 80 ms floor will not arm — this job
    # records that). Plus Crest-default on A/1 and A/600.
    jobs.append(
        {
            "name": "Crest_FarHoldFlag",
            "window": "B600",
            "csv": str(WINDOWS["B600"]),
            "spec": {"kind": "farhold"},
        }
    )
    for win in ("A1", "A600"):
        jobs.append(
            {
                "name": "Crest",
                "window": win,
                "csv": str(WINDOWS[win]),
                "spec": VARIANTS["Crest"],
            }
        )

    rows: list[dict] = []
    if args.workers <= 1:
        rows = [_job(j) for j in jobs]
    else:
        with ProcessPoolExecutor(max_workers=args.workers) as pool:
            futs = [pool.submit(_job, j) for j in jobs]
            for fut in as_completed(futs):
                rows.append(fut.result())

    (out_dir / "b600_variants.json").write_text(
        json.dumps(rows, indent=2) + "\n", encoding="utf-8"
    )
    pd.DataFrame(rows).to_csv(out_dir / "b600_variants.csv", index=False)
    print("\n=== variants ===")
    for r in sorted(rows, key=lambda x: (x["window"], x["variant"])):
        extra = ""
        if "reconfigs_detected" in r:
            extra = (
                f"  rec={r['reconfigs_detected']}"
                f"  ser_lite={r['ser_lite_count']}"
                f"  far_holds={r.get('far_holds', 0)}"
                f"  ca={r['ca_aborts']}"
                f"  ant={r['anticipator_holds']}"
                f"  reasons={r.get('reprobe_reasons')}"
            )
        print(
            f"{r['window']:5s} {r['variant']:18s}  gp={r['goodput_mbps']:7.2f}  "
            f"p95={r['p95_rtt_ms']:6.1f}  bw={r.get('mean_bw_mbps', 0):7.1f}{extra}"
        )
    print(f"Wrote {out_dir}")


if __name__ == "__main__":
    main()
