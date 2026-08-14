#!/usr/bin/env python3
"""Geometry-only walk of vendored zhao_zenodo23 slices. No CCA.

Bars (unchanged product absolute): gp mean ≥ 75 AND IRTT p95 mean ≤ 138.8.

Honesty:
  cubic-goodput oracle is a *lower bound* on path capacity. If the mean is
  < 75 → INCONCLUSIVE (not FAIL). If ≥ 75, gp PASS is conservative.
  p95 is native IRTT (10 ms UDP), not a CCA ACK p95 and not WetLinks hold-expand.

Usage:
  python -m experiments.zhao_zenodo23_geometry
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from leo_cc.network import LeoPathConfig, load_trace_csv, walk_path_geometry

GP_BAR = 75.0
P95_BAR = 138.8
DT_S = 0.05
ERA = "zhao_zenodo23"
DEFAULT_TRACES = ROOT / "traces" / "zhao_zenodo23"
DEFAULT_TAG = "20260813-v312-zhao-zenodo23-geom"


def duration_from_csv(path: Path) -> float:
    rows = load_trace_csv(path)
    last_t = rows[-1].t_s
    return last_t + DT_S


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--traces", type=Path, default=DEFAULT_TRACES)
    ap.add_argument("--tag", default=DEFAULT_TAG)
    args = ap.parse_args()
    traces = args.traces if args.traces.is_absolute() else (ROOT / args.traces)
    stats_path = traces / "session_stats.json"
    if not stats_path.is_file():
        raise SystemExit(f"missing {stats_path} — run ingest first")
    stats = json.loads(stats_path.read_text(encoding="utf-8"))
    sessions = stats.get("sessions") or []
    if len(sessions) != 5:
        raise SystemExit(f"expected 5 vendored sessions, got {len(sessions)}")

    out_dir = ROOT / "results" / "archive" / args.tag
    out_dir.mkdir(parents=True, exist_ok=True)

    rows = []
    for s in sessions:
        csv_path = traces / s["csv_name"]
        dur = duration_from_csv(csv_path)
        cfg = LeoPathConfig(
            duration_s=dur,
            dt_s=DT_S,
            trace_csv=str(csv_path),
            seed=0,
            path_profile="zhao_zenodo23",
        )
        g = walk_path_geometry(cfg)
        native_p95 = float(s["native_irtt_p95_ms"])
        native_oracle = float(s["native_oracle_cubic_gp_mbps"])
        rows.append(
            {
                "era": ERA,
                "quantile": s["quantile"],
                "rank_index": s["rank_index"],
                "session_id": s["session_id"],
                "start_utc": s["start_utc"],
                "csv": s["csv_name"],
                "duration_s": dur,
                "n_csv_rows": s["n_csv_rows"],
                "resampled_oracle_gp_mbps": g["oracle_gp_mbps"],
                "resampled_mean_cap_mbps": g["mean_cap_mbps"],
                "resampled_path_p95_ms": g["path_p95_ms"],
                "native_oracle_cubic_gp_mbps": native_oracle,
                "native_irtt_p50_ms": s["native_irtt_p50_ms"],
                "native_irtt_p95_ms": native_p95,
                "native_irtt_p99_ms": s["native_irtt_p99_ms"],
                "native_irtt_max_ms": s["native_irtt_max_ms"],
                "capacity_meaning": "tcp_cubic_downlink_goodput_lower_bound",
                "sqm": "unknown",
                "n_ho_labeled": 0,
            }
        )
        print(
            f"{s['quantile']} {s['session_id']}  "
            f"oracle_cubic={native_oracle:.2f}  irtt_p95={native_p95:.2f}  "
            f"resampled_oracle={g['oracle_gp_mbps']:.2f}  "
            f"resampled_p95={g['path_p95_ms']:.2f}",
            flush=True,
        )

    df = pd.DataFrame(rows)
    oracle_mean = float(df["native_oracle_cubic_gp_mbps"].mean())
    irtt_p95_mean = float(df["native_irtt_p95_ms"].mean())
    resampled_oracle_mean = float(df["resampled_oracle_gp_mbps"].mean())
    resampled_p95_mean = float(df["resampled_path_p95_ms"].mean())

    if oracle_mean + 1e-9 < GP_BAR:
        gp_verdict = "INCONCLUSIVE"
        gp_note = (
            "cubic-goodput oracle mean < 75; this is a TCP Cubic lower bound "
            "on path capacity, not a FAIL"
        )
    else:
        gp_verdict = "PASS"
        gp_note = (
            "cubic-goodput oracle mean ≥ 75; PASS is conservative because "
            "oracle is a lower bound (path may be higher than Cubic achieved)"
        )
    p95_pass = irtt_p95_mean <= P95_BAR + 1e-9
    p95_verdict = "PASS" if p95_pass else "FAIL"
    if gp_verdict == "PASS" and p95_pass:
        dual = "PASS (geometry only; cubic-gp lower bound; not a CCA lock)"
    elif gp_verdict == "INCONCLUSIVE":
        dual = "INCONCLUSIVE on gp (lower bound); p95=" + p95_verdict
    else:
        dual = "FAIL dual-gate"

    verdict = {
        "era": ERA,
        "cca": "none",
        "bars": {"gp_mean": GP_BAR, "p95_mean": P95_BAR, "p95_source": "native_IRTT_10ms"},
        "n_sessions": 5,
        "quantile_rule": stats.get("quantile_rule"),
        "oracle_cubic_gp_mean": oracle_mean,
        "irtt_p95_mean": irtt_p95_mean,
        "resampled_oracle_gp_mean": resampled_oracle_mean,
        "resampled_path_p95_mean": resampled_p95_mean,
        "gp_verdict": gp_verdict,
        "gp_note": gp_note,
        "p95_verdict": p95_verdict,
        "dual_gate": dual,
        "sqm": "unknown",
        "capacity_meaning": "TCP Cubic downlink goodput; lower bound; not dish PHY / RF Mbps",
        "product_lock": "unchanged (synthetic starlink_v1 / v3.9 Crest). this era is research-only.",
        "do_not_merge": True,
        "do_not_mix_with": ["wetlinks_v1", "starlink_v1_crest_scorecard"],
        "doi": stats.get("doi"),
        "license": stats.get("license"),
        "paper": stats.get("paper"),
    }
    df.to_csv(out_dir / "session_geometry.csv", index=False)
    (out_dir / "feasibility_verdict.json").write_text(
        json.dumps(verdict, indent=2) + "\n", encoding="utf-8"
    )

    table = [
        "# zhao_zenodo23 geometry (no CCA)",
        "",
        f"Oracle cubic-goodput mean **{oracle_mean:.2f}** Mbps → **{gp_verdict}** ({gp_note}).",
        f"IRTT p95 mean **{irtt_p95_mean:.2f}** ms → **{p95_verdict}** (bar ≤ {P95_BAR}).",
        f"Dual-gate: **{dual}**.",
        "",
        "SQM unknown. Capacity is TCP Cubic downlink goodput (lower bound), not dish PHY.",
        "No Crest / BBR / CUBIC sim on this cook. Do not merge. Do not mix with wetlinks_v1 or starlink_v1 82.09/76.26.",
        "",
        "| q | session_id | start UTC | oracle cubic-gp Mbps | IRTT p95 ms | resampled oracle | resampled path p95 |",
        "|---|------------|-----------|---------------------:|------------:|-----------------:|-------------------:|",
    ]
    for r in rows:
        table.append(
            f"| {r['quantile']} | `{r['session_id']}` | {r['start_utc']} | "
            f"{r['native_oracle_cubic_gp_mbps']:.2f} | {r['native_irtt_p95_ms']:.2f} | "
            f"{r['resampled_oracle_gp_mbps']:.2f} | {r['resampled_path_p95_ms']:.2f} |"
        )
    table += [
        f"| **mean** | | | **{oracle_mean:.2f}** | **{irtt_p95_mean:.2f}** | "
        f"**{resampled_oracle_mean:.2f}** | **{resampled_p95_mean:.2f}** |",
        "",
    ]
    (out_dir / "TABLE.md").write_text("\n".join(table) + "\n", encoding="utf-8")
    print("\n" + "\n".join(table))
    print(f"\nWrote {out_dir}")


if __name__ == "__main__":
    main()
