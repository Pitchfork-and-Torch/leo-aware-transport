#!/usr/bin/env python3
"""v3.13 leocc_v1: geometry first, then endpoint CCA on 5 downlink windows.

Era: leocc_v1. Never mix with starlink_v1 82.09/76.26, wetlinks_v1, zhao_zenodo23,
or ope_v36 58/152. Crest stays (LeoAwareCCA defaults). No Halo/QSP/PATHHINT.

Capacity is UDP saturation (continuous ~120 s, first 90 s). RTT = 2×OWD.
Not dish PHY. Not Current. Do not merge.

Usage:
  python3 -m experiments.run_leocc --geometry-only
  python3 -m experiments.run_leocc --tag 20260814-v313-leocc --workers 4
"""
from __future__ import annotations

import argparse
import json
import sys
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from experiments.slice_leocc import DURATION_S, OUT_DIR
from leo_cc.ccas import BbrCCA, CubicCCA, LeoAwareCCA
from leo_cc.harness import (
    PRODUCT_GP_BAR,
    PRODUCT_P95_BAR,
    PRODUCT_PATH_PROFILE,
    PRODUCT_SEEDS,
    PRODUCT_TERR_GP_BAR,
)
from leo_cc.metrics import summarize_result
from leo_cc.network import LeoPathConfig, walk_path_geometry
from leo_cc.sim import SOFT_QIR_ALPHA, run_sim

ERA = "leocc_v1"
SIM_DT_S = 0.01
CAPPED_BUFFER_BYTES = 250_000
# 1 MB → 8*buffer/dt = 800 Mbps at dt=0.01 (LeoCC downlink sat ~300–530 Mbps).
LEOCC_BUFFER_BYTES = 1_000_000


def send_ceiling_mbps(buffer_bytes: int, dt_s: float = SIM_DT_S) -> float:
    return 8.0 * float(buffer_bytes) / max(dt_s, 1e-12) / 1e6


def window_paths(trace_dir: Path) -> list[Path]:
    stats_path = trace_dir / "session_stats.json"
    if not stats_path.is_file():
        raise SystemExit(
            f"missing {stats_path}\nRun: python -m experiments.slice_leocc --zip /tmp/leocc/4.8K.zip"
        )
    stats = json.loads(stats_path.read_text(encoding="utf-8"))
    paths = [trace_dir / s["csv_name"] for s in stats["sessions"]]
    missing = [p for p in paths if not p.exists()]
    if missing:
        raise SystemExit("missing LeoCC windows:\n  " + "\n  ".join(str(p) for p in missing))
    return paths


def window_cfg(
    path: Path,
    dt_s: float = SIM_DT_S,
    buffer_bytes: int = LEOCC_BUFFER_BYTES,
) -> LeoPathConfig:
    return LeoPathConfig(
        duration_s=DURATION_S,
        dt_s=dt_s,
        seed=0,
        path_profile=ERA,
        trace_csv=str(path),
        buffer_bytes=int(buffer_bytes),
    )


def geometry_table(trace_dir: Path) -> pd.DataFrame:
    stats = json.loads((trace_dir / "session_stats.json").read_text(encoding="utf-8"))
    by_csv = {s["csv_name"]: s for s in stats["sessions"]}
    rows = []
    for path in window_paths(trace_dir):
        g = walk_path_geometry(window_cfg(path, dt_s=0.05))
        meta = by_csv[path.name]
        g["window_id"] = path.stem
        g["quantile"] = meta["quantile"]
        g["site"] = meta["site"]
        g["trace_no"] = meta["trace_no"]
        g["native_owd_p95_ms"] = meta["native_owd_p95_ms"]
        g["native_rtt_p95_ms"] = meta["native_rtt_p95_ms"]
        g["native_oracle_udp_mbps"] = meta["native_oracle_udp_mbps"]
        rows.append(g)
    return pd.DataFrame(rows)


def verdict_from_geometry(df: pd.DataFrame) -> dict:
    # Gate p95 is native 2×OWD (10 ms ICMP), not the 50 ms resample smear.
    oracle_mean = float(df["native_oracle_udp_mbps"].mean())
    path_p95_mean = float(df["native_rtt_p95_ms"].mean())
    owd_p95_mean = float(df["native_owd_p95_ms"].mean())
    resampled_oracle = float(df["oracle_gp_mbps"].mean())
    resampled_p95 = float(df["path_p95_ms"].mean())
    gp_possible = oracle_mean >= PRODUCT_GP_BAR - 1e-9
    p95_possible = path_p95_mean <= PRODUCT_P95_BAR + 1e-9
    return {
        "era": ERA,
        "n_windows": int(len(df)),
        "oracle_gp_mean": oracle_mean,
        "path_p95_mean": path_p95_mean,
        "owd_p95_mean": owd_p95_mean,
        "resampled_oracle_gp_mean": resampled_oracle,
        "resampled_path_p95_mean": resampled_p95,
        "gp_ge_75_possible": gp_possible,
        "p95_le_138_8_possible": p95_possible,
        "absolute_dual_gate_possible": gp_possible and p95_possible,
        "soft_qir_alpha": SOFT_QIR_ALPHA,
        "rtt_rule": "2 * one-way delay",
        "capacity_meaning": "UDP iperf3 saturation; not dish PHY",
        "bars": {"gp_mean": PRODUCT_GP_BAR, "p95_mean": PRODUCT_P95_BAR},
        "note": (
            "Geometry uses first 90s of LeoCC downlink UDP-sat + ICMP OWD. "
            "p95 bar is native 2×OWD. Do not mix with starlink_v1 / wetlinks_v1 / zhao."
        ),
    }


_CCA_CLS = {"CUBIC": CubicCCA, "BBRv3approx": BbrCCA, "LeoAware": LeoAwareCCA}


def _cca_job(payload: dict) -> dict:
    """One (window, CCA) pair. Top-level so ProcessPoolExecutor can pickle it."""
    name = payload["cca"]
    path = Path(payload["csv"])
    buffer_bytes = int(payload["buffer_bytes"])
    ceiling = send_ceiling_mbps(buffer_bytes)
    print(
        f"cca {path.stem} {name}  buffer={buffer_bytes}  "
        f"ceiling={ceiling:.0f}Mbps ...",
        flush=True,
    )
    cfg = window_cfg(path, buffer_bytes=buffer_bytes)
    res = run_sim(_CCA_CLS[name], cfg=cfg, n_flows=1)
    m = summarize_result(res)[0]
    return {
        "era": ERA,
        "window_id": path.stem,
        "cca": name,
        "buffer_bytes": buffer_bytes,
        "send_ceiling_mbps": ceiling,
        "goodput_mbps": m.goodput_bps / 1e6,
        "p95_rtt_ms": m.p95_rtt_s * 1000,
        "p95_path_rtt_ms": m.p95_path_rtt_s * 1000,
        "p95_excess_rtt_ms": m.p95_excess_rtt_s * 1000,
        "mean_excess_rtt_ms": m.mean_excess_rtt_s * 1000,
        "handovers": len(res.handovers),
        "soft_qir_alpha": res.soft_qir_alpha,
    }


def run_window_cca(
    trace_dir: Path, buffer_bytes: int, workers: int = 1
) -> pd.DataFrame:
    jobs = [
        {"csv": str(path), "cca": name, "buffer_bytes": buffer_bytes}
        for path in window_paths(trace_dir)
        for name in ("CUBIC", "BBRv3approx", "LeoAware")
    ]
    if workers <= 1:
        return pd.DataFrame([_cca_job(j) for j in jobs])
    rows: list[dict] = []
    with ProcessPoolExecutor(max_workers=workers) as pool:
        futs = [pool.submit(_cca_job, j) for j in jobs]
        for fut in as_completed(futs):
            row = fut.result()
            print(
                f"done {row['window_id']} {row['cca']}  "
                f"gp={row['goodput_mbps']:.2f}  p95={row['p95_rtt_ms']:.2f}",
                flush=True,
            )
            rows.append(row)
    return pd.DataFrame(rows)


def run_terr_control() -> pd.DataFrame:
    rows = []
    for seed in PRODUCT_SEEDS:
        cfg = LeoPathConfig(duration_s=60, seed=seed, terrestrial=True)
        print(f"cca terrestrial seed={seed} LeoAware ...", flush=True)
        res = run_sim(LeoAwareCCA, cfg=cfg, n_flows=1)
        m = summarize_result(res)[0]
        rows.append(
            {
                "era": "synthetic_terrestrial",
                "window_id": f"terr_seed{seed}",
                "cca": "LeoAware",
                "goodput_mbps": m.goodput_bps / 1e6,
                "p95_rtt_ms": m.p95_rtt_s * 1000,
                "p95_path_rtt_ms": m.p95_path_rtt_s * 1000,
                "p95_excess_rtt_ms": m.p95_excess_rtt_s * 1000,
                "mean_excess_rtt_ms": m.mean_excess_rtt_s * 1000,
                "handovers": len(res.handovers),
                "soft_qir_alpha": res.soft_qir_alpha,
            }
        )
    return pd.DataFrame(rows)


def scorecard(
    geo_v: dict,
    cca_df: pd.DataFrame | None,
    terr_df: pd.DataFrame | None,
    buffer_bytes: int,
) -> dict:
    if cca_df is None or terr_df is None:
        return {
            "era": ERA,
            "product_lock_era": PRODUCT_PATH_PROFILE,
            "cook": "leocc_v1_geometry",
            "decision": "REJECT" if not geo_v["absolute_dual_gate_possible"] else "GEOMETRY_ONLY",
            "cca": "none",
            "soft_qir_alpha": SOFT_QIR_ALPHA,
            "geometry": geo_v,
            "gates": {
                "geometry_dual_gate": geo_v["absolute_dual_gate_possible"],
                "gp_ge_75": geo_v["gp_ge_75_possible"],
                "p95_le_138_8": geo_v["p95_le_138_8_possible"],
            },
            "do_not_merge": True,
            "do_not_mix_with": [
                "wetlinks_v1",
                "zhao_zenodo23",
                "starlink_v1_crest_scorecard",
                "ope_v36",
            ],
            "note": (
                "Geometry-only stop. No Current. No paid. Product lock stays "
                "synthetic starlink_v1 / v3.9 Crest."
            ),
        }

    def means(df: pd.DataFrame, cca: str) -> tuple[float, float]:
        g = df[df["cca"] == cca]
        return float(g["goodput_mbps"].mean()), float(g["p95_rtt_ms"].mean())

    leo_gp, leo_p95 = means(cca_df, "LeoAware")
    bbr_gp, bbr_p95 = means(cca_df, "BBRv3approx")
    cub_gp, cub_p95 = means(cca_df, "CUBIC")
    terr_gp = float(terr_df["goodput_mbps"].mean())
    terr_p95 = float(terr_df["p95_rtt_ms"].mean())
    gp_ok = leo_gp >= PRODUCT_GP_BAR
    p95_ok = leo_p95 <= PRODUCT_P95_BAR
    terr_ok = terr_gp >= PRODUCT_TERR_GP_BAR
    crest_clears_bbr = leo_gp > bbr_gp + 1e-9
    p95_vs_bbr = leo_p95 <= bbr_p95 + 1e-9
    abs_ok = bool(geo_v["absolute_dual_gate_possible"] and gp_ok and p95_ok and terr_ok)
    pareto_bbr = crest_clears_bbr and p95_vs_bbr
    if abs_ok and pareto_bbr:
        decision = "ACCEPT"
        decision_note = (
            "absolute dual-gate PASS and Crest Pareto vs BBR on this era. "
            "Not Current. No paid. Do not merge."
        )
    elif abs_ok:
        decision = "ACCEPT_ERA_REJECT_BBR"
        decision_note = (
            "absolute 75/138.8 PASS on leocc_v1 means; Crest does not clear BBR. "
            "Not Current. No paid. Do not merge."
        )
    else:
        decision = "REJECT"
        decision_note = (
            "absolute dual-gate FAIL on leocc_v1 CCA means. Not Current. Do not merge."
        )
    ceiling = send_ceiling_mbps(buffer_bytes)
    return {
        "era": ERA,
        "product_lock_era": PRODUCT_PATH_PROFILE,
        "cook": "leocc_v1",
        "decision": decision,
        "decision_note": decision_note,
        "soft_qir_alpha": SOFT_QIR_ALPHA,
        "buffer_bytes": buffer_bytes,
        "send_ceiling_mbps": ceiling,
        "geometry": geo_v,
        "windows": {
            "LeoAware_gp_mean": leo_gp,
            "LeoAware_p95_mean": leo_p95,
            "BBR_gp_mean": bbr_gp,
            "BBR_p95_mean": bbr_p95,
            "CUBIC_gp_mean": cub_gp,
            "CUBIC_p95_mean": cub_p95,
        },
        "terrestrial": {
            "LeoAware_gp_mean": terr_gp,
            "LeoAware_p95_mean": terr_p95,
            "note": "synthetic terrestrial control at product 250 KB; not a LeoCC window",
        },
        "gates": {
            "geometry_dual_gate": geo_v["absolute_dual_gate_possible"],
            "gp_ge_75": gp_ok,
            "p95_le_138_8": p95_ok,
            "terr_ge_77": terr_ok,
            "crest_gp_clears_bbr": crest_clears_bbr,
            "crest_p95_le_bbr": p95_vs_bbr,
            "absolute_dual_gate": abs_ok,
            "pareto_vs_bbr": pareto_bbr,
        },
        "do_not_merge": True,
        "do_not_mix_with": [
            "wetlinks_v1",
            "zhao_zenodo23",
            "starlink_v1_crest_scorecard",
            "ope_v36",
        ],
        "note": (
            "leocc_v1 research era. Continuous ≥90s UDP-sat + ICMP OWD (RTT=2×OWD). "
            f"dt={SIM_DT_S}; buffer={buffer_bytes} B; send ceiling {ceiling:.0f} Mbps. "
            "Not dish PHY. Crest defaults unchanged. No Current bump. No merge. "
            "Do not mix with wetlinks_v1, zhao_zenodo23, or starlink_v1 82.09/76.26."
        ),
    }


def write_table(out_dir: Path, geo: pd.DataFrame, verdict: dict, card: dict) -> None:
    lines = [
        "# leocc_v1 scorecard (v3.13)",
        "",
        f"Decision: **{card['decision']}**. {card.get('decision_note') or card.get('note')}",
        "",
        f"Oracle UDP-sat mean **{verdict['oracle_gp_mean']:.2f}** Mbps → "
        f"**{'PASS' if verdict['gp_ge_75_possible'] else 'FAIL'}** (bar ≥ 75).",
        f"Native 2×OWD p95 mean **{verdict['path_p95_mean']:.2f}** ms → "
        f"**{'PASS' if verdict['p95_le_138_8_possible'] else 'FAIL'}** (bar ≤ 138.8).",
        f"Native OWD p95 mean {verdict['owd_p95_mean']:.2f} ms (diagnostic).",
        "",
        "Capacity is UDP saturation, not dish PHY. RTT = 2 × LeoReplayer OWD.",
        "Not Current. Do not merge. Do not mix with wetlinks_v1 / zhao / starlink_v1 Crest.",
        "",
        "| q | site | trace | native UDP-sat oracle | OWD p95 | 2×OWD p95 | resampled oracle | resampled path p95 |",
        "|---|------|------:|----------------------:|--------:|----------:|-----------------:|-------------------:|",
    ]
    for _, r in geo.iterrows():
        lines.append(
            f"| {r['quantile']} | {r['site']} | {int(r['trace_no'])} | "
            f"{r['native_oracle_udp_mbps']:.2f} | {r['native_owd_p95_ms']:.2f} | "
            f"{r['native_rtt_p95_ms']:.2f} | {r['oracle_gp_mbps']:.2f} | "
            f"{r['path_p95_ms']:.2f} |"
        )
    lines.append(
        f"| **mean** | | | **{verdict['oracle_gp_mean']:.2f}** | "
        f"**{verdict['owd_p95_mean']:.2f}** | **{verdict['path_p95_mean']:.2f}** | "
        f"**{verdict['resampled_oracle_gp_mean']:.2f}** | "
        f"**{verdict['resampled_path_p95_mean']:.2f}** |"
    )
    wins = card.get("windows")
    if wins:
        lines += [
            "",
            "### CCA means (5 downlink windows, dt=0.01, 1 MB buffer)",
            "",
            "| CCA | gp mean | p95 mean |",
            "|-----|--------:|---------:|",
            f"| CUBIC | {wins['CUBIC_gp_mean']:.2f} | {wins['CUBIC_p95_mean']:.2f} |",
            f"| BBRv3approx | {wins['BBR_gp_mean']:.2f} | {wins['BBR_p95_mean']:.2f} |",
            f"| **LeoAware Crest** | **{wins['LeoAware_gp_mean']:.2f}** | **{wins['LeoAware_p95_mean']:.2f}** |",
            "",
            f"Terrestrial LeoAware {card['terrestrial']['LeoAware_gp_mean']:.2f} @ "
            f"{card['terrestrial']['LeoAware_p95_mean']:.1f} ms.",
        ]
    (out_dir / "TABLE.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--tag", default="20260814-v313-leocc")
    ap.add_argument("--trace-dir", type=Path, default=OUT_DIR)
    ap.add_argument("--buffer-bytes", type=int, default=LEOCC_BUFFER_BYTES)
    ap.add_argument("--geometry-only", action="store_true")
    ap.add_argument(
        "--workers",
        type=int,
        default=4,
        help="Process pool size for (window, CCA) jobs. 1 = sequential.",
    )
    args = ap.parse_args()
    buffer_bytes = int(args.buffer_bytes)
    out_dir = ROOT / "results" / "archive" / args.tag
    out_dir.mkdir(parents=True, exist_ok=True)

    geo = geometry_table(args.trace_dir)
    verdict = verdict_from_geometry(geo)
    geo.to_csv(out_dir / "path_geometry.csv", index=False)
    (out_dir / "feasibility_verdict.json").write_text(
        json.dumps(verdict, indent=2) + "\n", encoding="utf-8"
    )
    print("=== leocc_v1 geometry (5 downlink windows) ===")
    cols = [
        "quantile",
        "site",
        "trace_no",
        "native_oracle_udp_mbps",
        "native_owd_p95_ms",
        "native_rtt_p95_ms",
        "oracle_gp_mbps",
        "path_p95_ms",
    ]
    print(geo[cols].to_string(index=False, float_format=lambda x: f"{x:.2f}"))
    print(
        f"MEANS  oracle_gp={verdict['oracle_gp_mean']:.2f}  "
        f"rtt_p95={verdict['path_p95_mean']:.2f}  "
        f"owd_p95={verdict['owd_p95_mean']:.2f}"
    )
    print(
        f"VERDICT  gp≥75 possible={verdict['gp_ge_75_possible']}  "
        f"p95≤138.8 possible={verdict['p95_le_138_8_possible']}  "
        f"absolute dual-gate possible={verdict['absolute_dual_gate_possible']}"
    )

    if not verdict["absolute_dual_gate_possible"]:
        card = scorecard(verdict, None, None, buffer_bytes)
        (out_dir / "scorecard.json").write_text(
            json.dumps(card, indent=2) + "\n", encoding="utf-8"
        )
        write_table(out_dir, geo, verdict, card)
        print(
            "STOP: leocc_v1 geometry fails the absolute bars. "
            "No CCA cook. No quiet rebaseline.",
            flush=True,
        )
        print(f"Wrote {out_dir}")
        return

    if args.geometry_only:
        card = scorecard(verdict, None, None, buffer_bytes)
        (out_dir / "scorecard.json").write_text(
            json.dumps(card, indent=2) + "\n", encoding="utf-8"
        )
        write_table(out_dir, geo, verdict, card)
        print("geometry-only: bars possible; skip CCA this invocation")
        print(f"Wrote {out_dir}")
        return

    if send_ceiling_mbps(buffer_bytes) < 550.0 - 1e-9:
        raise SystemExit(
            f"buffer {buffer_bytes} B has send ceiling "
            f"{send_ceiling_mbps(buffer_bytes):.1f} Mbps < 550. "
            "Raise buffer (1 MB → 800 Mbps at dt=0.01)."
        )
    print(
        f"buffer={buffer_bytes} B  send_ceiling="
        f"{send_ceiling_mbps(buffer_bytes):.0f} Mbps  "
        f"workers={max(1, int(args.workers))}  "
        f"(product default stays {CAPPED_BUFFER_BYTES} B)",
        flush=True,
    )
    cca_df = run_window_cca(
        args.trace_dir, buffer_bytes=buffer_bytes, workers=max(1, int(args.workers))
    )
    terr_df = run_terr_control()
    cca_df.to_csv(out_dir / "window_cca.csv", index=False)
    terr_df.to_csv(out_dir / "terr_control.csv", index=False)
    card = scorecard(verdict, cca_df, terr_df, buffer_bytes=buffer_bytes)
    (out_dir / "scorecard.json").write_text(
        json.dumps(card, indent=2) + "\n", encoding="utf-8"
    )
    write_table(out_dir, geo, verdict, card)
    print("\n=== 5-window CCA means ===")
    print(
        cca_df.groupby("cca")[["goodput_mbps", "p95_rtt_ms"]]
        .mean()
        .to_string(float_format=lambda x: f"{x:.3f}")
    )
    print(
        f"terr LeoAware gp={card['terrestrial']['LeoAware_gp_mean']:.3f}  "
        f"p95={card['terrestrial']['LeoAware_p95_mean']:.3f}"
    )
    print(f"DECISION {card['decision']}")
    print(f"Wrote {out_dir}")


if __name__ == "__main__":
    main()
