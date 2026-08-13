#!/usr/bin/env python3
"""
Lightweight CLI explorer for LEO scenarios (stretch goal).

Examples:
  python -m experiments.cli_explore --cca LeoAware --ho 15 --duration 45
  python -m experiments.cli_explore --cca CUBIC --terrestrial
  python -m experiments.cli_explore --cca LeoAware --flows 3 --isl
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from leo_cc.network import LeoPathConfig
from leo_cc.ccas import CubicCCA, BbrCCA, LeoAwareCCA
from leo_cc.sim import run_sim
from leo_cc.metrics import summarize_result, jain_fairness
from leo_cc.plotting import plot_timeseries

CCAS = {
    "CUBIC": CubicCCA,
    "BBRv3approx": BbrCCA,
    "LeoAware": LeoAwareCCA,
}


def main() -> None:
    p = argparse.ArgumentParser(description="LeoAware transport scenario explorer")
    p.add_argument("--cca", choices=list(CCAS), default="LeoAware")
    p.add_argument("--duration", type=float, default=60.0)
    p.add_argument("--ho", type=float, default=22.0, help="handover interval seconds")
    p.add_argument("--flows", type=int, default=1)
    p.add_argument("--seed", type=int, default=7)
    p.add_argument("--terrestrial", action="store_true")
    p.add_argument("--isl", action="store_true")
    p.add_argument("--hints", action="store_true", help="LeoAware only: use path hints")
    p.add_argument(
        "--path-profile",
        default="starlink_v1",
        help="starlink_v1 (product) or ope_v36 (research)",
    )
    p.add_argument("--out", type=Path, default=ROOT / "results" / "cli_explore.png")
    args = p.parse_args()

    from leo_cc.harness import apply_profile, resolve_path_profile

    cfg = LeoPathConfig(
        duration_s=args.duration,
        handover_interval_s=args.ho,
        seed=args.seed,
        terrestrial=args.terrestrial,
        isl_enabled=args.isl,
    )
    if not args.terrestrial:
        cfg = apply_profile(cfg, resolve_path_profile(args.path_profile))

    def factory():
        if args.cca == "LeoAware":
            return LeoAwareCCA(use_path_hints=args.hints)
        return CCAS[args.cca]()

    res = run_sim(factory, cfg=cfg, n_flows=args.flows)
    metrics = summarize_result(res)
    thr = [m.goodput_bps for m in metrics]
    fair = jain_fairness(thr) if args.flows > 1 else 1.0

    print(f"CCA={args.cca}  duration={args.duration}s  handovers={len(res.handovers)}")
    for m in metrics:
        print(
            f"  flow={m.name}: goodput={m.goodput_bps/1e6:.2f} Mbps  "
            f"p95_rtt={m.p95_rtt_s*1000:.1f} ms  loss={m.loss_rate:.4f}"
        )
    if args.flows > 1:
        print(f"  Jain fairness={fair:.3f}")
    if args.cca == "LeoAware" and args.flows == 1:
        # factory already discarded; re-run detect count not available on result
        pass

    plot_timeseries(res, args.out, title=f"CLI {args.cca}")
    print(f"Wrote {args.out}")


if __name__ == "__main__":
    main()
