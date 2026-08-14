#!/usr/bin/env python3
"""Cut 5×90s WetLinks windows into the existing LeoPath CSV contract.

Source: sys-uos/WetLinks (Laniewski et al., TMA 2024), CC BY-SA 4.0.
Uses merged analysis_data (15s UDP iperf mean + nearest ping aggregate).

WetLinks is not a continuous 90s 50ms path: iperf runs are 15s every ~3 min
and ping is a ~49s / 250-packet aggregate. This slicer hold-expands one
measurement cycle to 90s and documents every inference. It does not
synthesize a generative Starlink path.

Usage:
  python -m experiments.slice_wetlinks --fetch
  python -m experiments.slice_wetlinks --cache /tmp/wetlinks
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
import urllib.request
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

OUT_DIR = ROOT / "traces" / "wetlinks"
DEFAULT_CACHE = Path("/tmp/wetlinks")
DURATION_S = 90.0
DT_S = 0.05
RECONFIG_T_S = 12.0
RECONFIG_WINDOW_S = 0.4
JUMP_MS = 20.0

SOURCES = {
    "enschede": {
        "filename": "analysis_data_Enschede.csv",
        "url": (
            "https://raw.githubusercontent.com/sys-uos/WetLinks/main/"
            "Preprocessed_Data/analysis_data_Enschede.csv"
        ),
    },
    "osnabruck": {
        "filename": "analysis_data_Osnabruck.csv",
        "url": (
            "https://raw.githubusercontent.com/sys-uos/WetLinks/main/"
            "Preprocessed_Data/analysis_data_Osnabr%C3%BCck.csv"
        ),
    },
}

# Deterministic calendar-spread picks (not cherry-picked for gp/p95).
# index = round(quantile * (n_valid - 1)) after the validity filter below.
WINDOW_SPECS = (
    ("w1_enschede_20231110T091227", "enschede", 0.20),
    ("w2_enschede_20240215T153911", "enschede", 0.80),
    ("w3_osnabruck_20230930T061825", "osnabruck", 0.10),
    ("w4_osnabruck_20231220T160942", "osnabruck", 0.50),
    ("w5_osnabruck_20240223T171843", "osnabruck", 0.90),
)


@dataclass
class WindowSource:
    window_id: str
    site: str
    source_file: str
    source_row: int
    timestamp_start: str
    timestamp_end: str
    iperf_download_mbps: float
    iperf_download_std_mbps: float
    ping_avg_ms: float
    ping_worst_ms: float
    ping_best_ms: float
    ping_stddev_ms: float
    ping_loss_p: float
    inferred_reconfig: bool
    measured_coverage_s: float
    hold_s: float


def fetch_analysis(cache: Path) -> None:
    cache.mkdir(parents=True, exist_ok=True)
    for spec in SOURCES.values():
        dest = cache / spec["filename"]
        if dest.exists() and dest.stat().st_size > 1_000_000:
            print(f"cache hit {dest}", flush=True)
            continue
        print(f"fetch {spec['url']} -> {dest}", flush=True)
        try:
            urllib.request.urlretrieve(spec["url"], dest)
        except Exception as exc:  # noqa: BLE001 — must STOP, not invent
            raise SystemExit(
                f"WETLINKS_FETCH_BLOCKED: could not download {spec['url']}: {exc}\n"
                "STOP. Do not invent traces or fall back to starlink_v2."
            ) from exc
        if dest.stat().st_size < 1_000_000:
            raise SystemExit(
                f"WETLINKS_FETCH_BLOCKED: {dest} is too small "
                f"({dest.stat().st_size} bytes). STOP."
            )


def _load_valid(path: Path, site: str):
    import pandas as pd

    df = pd.read_csv(path)
    df["site"] = site
    df["timestamp_start"] = pd.to_datetime(df["timestamp_start"])
    df["timestamp_end"] = pd.to_datetime(df["timestamp_end"])
    df["cap_mbps"] = df["download"] / 1e6
    df["download_std_mbps"] = df["download_std"] / 1e6
    valid = df.dropna(subset=["cap_mbps", "ping_avg", "ping_worst", "ping_best"])
    valid = valid[
        (valid["cap_mbps"] > 1.0)
        & (valid["ping_avg"] > 5.0)
        & (valid["ping_avg"] < 500.0)
    ]
    return valid.sort_values("timestamp_start").reset_index(drop=True)


def pick_rows(cache: Path) -> list[tuple[str, object]]:
    frames = {}
    for site, spec in SOURCES.items():
        path = cache / spec["filename"]
        if not path.exists():
            raise SystemExit(
                f"WETLINKS_FETCH_BLOCKED: missing {path}. Re-run with --fetch. STOP."
            )
        frames[site] = _load_valid(path, site)
        if frames[site].empty:
            raise SystemExit(f"no valid WetLinks rows in {path}. STOP.")
    picked = []
    for window_id, site, q in WINDOW_SPECS:
        df = frames[site]
        idx = int(round(q * (len(df) - 1)))
        row = df.iloc[idx]
        picked.append((window_id, row))
    return picked


def window_meta(window_id: str, row) -> WindowSource:
    loss_p = float(row["ping_packet_loss"]) / 100.0
    if loss_p != loss_p:  # NaN
        loss_p = 0.0
    std_mbps = float(row["download_std_mbps"])
    if std_mbps != std_mbps:
        std_mbps = 0.0
    jump = float(row["ping_worst"]) - float(row["ping_avg"]) >= JUMP_MS
    return WindowSource(
        window_id=window_id,
        site=str(row["site"]),
        source_file=SOURCES[str(row["site"])]["filename"],
        source_row=int(row.name),
        timestamp_start=str(row["timestamp_start"])[:19],
        timestamp_end=str(row["timestamp_end"])[:19],
        iperf_download_mbps=float(row["cap_mbps"]),
        iperf_download_std_mbps=std_mbps,
        ping_avg_ms=float(row["ping_avg"]),
        ping_worst_ms=float(row["ping_worst"]),
        ping_best_ms=float(row["ping_best"]),
        ping_stddev_ms=float(row["ping_stddev"]) if row["ping_stddev"] == row["ping_stddev"] else 0.0,
        ping_loss_p=loss_p,
        inferred_reconfig=jump,
        measured_coverage_s=15.0,
        hold_s=75.0,
    )


def write_window_csv(path: Path, meta: WindowSource) -> None:
    """Hold-expand one WetLinks cycle onto t_s,rtt_ms,capacity_mbps,loss_p,reconfig."""
    path.parent.mkdir(parents=True, exist_ok=True)
    n = int(round(DURATION_S / DT_S))
    with path.open("w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(["t_s", "rtt_ms", "capacity_mbps", "loss_p", "reconfig"])
        fired = False
        for i in range(n):
            t = i * DT_S
            rtt = meta.ping_avg_ms
            loss = meta.ping_loss_p
            reconfig = 0
            if meta.inferred_reconfig and RECONFIG_T_S <= t < RECONFIG_T_S + RECONFIG_WINDOW_S:
                rtt = meta.ping_worst_ms
                if not fired:
                    reconfig = 1
                    fired = True
            w.writerow(
                [
                    f"{t:.4f}",
                    f"{rtt:.3f}",
                    f"{meta.iperf_download_mbps:.4f}",
                    f"{loss:.6f}",
                    reconfig,
                ]
            )


def slice_windows(cache: Path, out_dir: Path) -> list[WindowSource]:
    picked = pick_rows(cache)
    metas: list[WindowSource] = []
    out_dir.mkdir(parents=True, exist_ok=True)
    for window_id, row in picked:
        meta = window_meta(window_id, row)
        write_window_csv(out_dir / f"{window_id}.csv", meta)
        metas.append(meta)
        print(
            f"wrote {window_id}  site={meta.site}  "
            f"t={meta.timestamp_start}  cap={meta.iperf_download_mbps:.2f}  "
            f"rtt_avg={meta.ping_avg_ms:.2f}  rtt_worst={meta.ping_worst_ms:.2f}  "
            f"reconfig={meta.inferred_reconfig}",
            flush=True,
        )
    (out_dir / "windows.json").write_text(
        json.dumps(
            {
                "era": "wetlinks_v1",
                "citation": (
                    "D. Laniewski, E. Lanfer, B. Meijerink, "
                    "R. van Rijswijk-Deij, N. Aschenbruck, "
                    "WetLinks: a Large-Scale Longitudinal Starlink Dataset "
                    "with Contiguous Weather Data, Proc. TMA 2024. "
                    "https://github.com/sys-uos/WetLinks"
                ),
                "license": "CC BY-SA 4.0",
                "sliced_at_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                "inferences": {
                    "capacity": (
                        "UDP iperf download mean (15s) held for 90s. "
                        "Saturated-flow goodput proxy, not dish PHY."
                    ),
                    "rtt": (
                        "ping_avg held; if ping_worst-ping_avg>=20ms, one 0.4s "
                        "spike to ping_worst at t=12.0 (timing inferred; "
                        "WetLinks ping is a 49s aggregate)."
                    ),
                    "loss_p": "ping_packet_loss / 100 (measured aggregate).",
                    "reconfig": "1 on the first slot of the inferred RTT spike.",
                    "not_done": (
                        "No generative HO cadence. No starlink_v2. "
                        "No invented 1s ping series."
                    ),
                },
                "windows": [asdict(m) for m in metas],
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    return metas


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--cache", type=Path, default=DEFAULT_CACHE)
    ap.add_argument(
        "--fetch",
        action="store_true",
        help="download WetLinks analysis_data CSVs into --cache",
    )
    ap.add_argument("--out", type=Path, default=OUT_DIR)
    args = ap.parse_args()
    if args.fetch:
        fetch_analysis(args.cache)
    slice_windows(args.cache, args.out)
    print(f"wrote {args.out}", flush=True)


if __name__ == "__main__":
    main()
