#!/usr/bin/env python3
"""Slice Zhao/Pan/Cai Zenodo dump → 5 calendar-quantile replay CSVs.

Research era `zhao_zenodo23` only. No CCA. Does not invent traces.

Source dump (download yourself; never commit):
  https://zenodo.org/records/10020034
  file: data-20230913-20230917.tar.zst
  DOI: 10.5281/zenodo.10020034  (CC-BY-4.0)

Usage:
  python -m experiments.zhao_zenodo23_ingest \\
      --extract-dir /tmp/zhao_zenodo23/extract \\
      --out traces/zhao_zenodo23
"""
from __future__ import annotations

import argparse
import csv
import json
import math
import re
import sys
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

DT_S = 0.05
MIN_DURATION_S = 90.0
QUANTILES = (0.0, 0.25, 0.50, 0.75, 1.0)
IRTT_NAME = re.compile(r"^irtt-10ms-2m-(\d{4}-\d{2}-\d{2}-\d{2}-\d{2}-\d{2})\.json$")
IPERF_NAME = re.compile(r"^iperf3-2m-(\d{4}-\d{2}-\d{2}-\d{2}-\d{2}-\d{2})\.json$")
LOST_OK = {"false", "0", ""}


def _pct(xs: list[float], p: float) -> float:
    if not xs:
        return float("nan")
    s = sorted(xs)
    if len(s) == 1:
        return s[0]
    k = (p / 100.0) * (len(s) - 1)
    lo = int(math.floor(k))
    hi = int(math.ceil(k))
    if lo == hi:
        return s[lo]
    w = k - lo
    return s[lo] * (1.0 - w) + s[hi] * w


def nearest_rank_index(n: int, q: float) -> int:
    """Round-half-up index into a 0..n-1 sorted list. Documented quantile rule."""
    if n <= 0:
        raise ValueError("empty list")
    return min(n - 1, int(q * (n - 1) + 0.5))


def parse_session_id(sid: str) -> datetime:
    return datetime.strptime(sid, "%Y-%m-%d-%H-%M-%S").replace(tzinfo=timezone.utc)


def load_irtt_header(path: Path) -> dict:
    """Parse IRTT JSON up to `round_trips` so we can filter without 13 MB/session."""
    with path.open("rb") as f:
        buf = b""
        while True:
            chunk = f.read(65536)
            if not chunk:
                break
            buf += chunk
            i = buf.find(b'"round_trips"')
            if i != -1:
                prefix = buf[:i].rstrip().rstrip(b",")
                return json.loads(prefix + b"}")
    return json.loads(buf)


def index_pairs(extract_dir: Path) -> list[tuple[str, Path, Path]]:
    data_root = extract_dir / "data"
    if not data_root.is_dir():
        # tarball may unpack with data/ at extract_dir or nested
        if (extract_dir / "2023-09-13").is_dir():
            data_root = extract_dir
        else:
            raise FileNotFoundError(f"no data/ under {extract_dir}")
    irtts: dict[str, Path] = {}
    iperfs: dict[str, Path] = {}
    for day in sorted(data_root.iterdir()):
        if not day.is_dir():
            continue
        for p in day.iterdir():
            m = IRTT_NAME.match(p.name)
            if m:
                irtts[m.group(1)] = p
                continue
            m = IPERF_NAME.match(p.name)
            if m:
                iperfs[m.group(1)] = p
    common = sorted(set(irtts) & set(iperfs), key=parse_session_id)
    return [(sid, irtts[sid], iperfs[sid]) for sid in common]


def iperf_duration_s(path: Path) -> tuple[float, int, str, str]:
    with path.open(encoding="utf-8") as f:
        ip = json.load(f)
    end = ip.get("end") or {}
    sr = end.get("sum_received") or end.get("sum") or {}
    dur = float(sr.get("seconds") or 0.0)
    nint = len(ip.get("intervals") or [])
    return (
        dur,
        nint,
        str(end.get("sender_tcp_congestion") or ""),
        str(end.get("receiver_tcp_congestion") or ""),
    )


def irtt_duration_s(path: Path) -> float:
    h = load_irtt_header(path)
    return float((h.get("stats") or {}).get("duration") or 0.0) / 1e9


def valid_pairs(pairs: list[tuple[str, Path, Path]]) -> list[tuple[str, Path, Path, dict]]:
    out = []
    for sid, irtt_p, iperf_p in pairs:
        try:
            ip_dur, nint, send_cc, recv_cc = iperf_duration_s(iperf_p)
            ir_dur = irtt_duration_s(irtt_p)
        except (json.JSONDecodeError, OSError, ValueError, TypeError) as e:
            print(f"skip {sid}: parse error {e}", flush=True)
            continue
        rec = {
            "session_id": sid,
            "irtt_duration_s": ir_dur,
            "iperf_duration_s": ip_dur,
            "n_iperf_intervals": nint,
            "sender_tcp_congestion": send_cc,
            "receiver_tcp_congestion": recv_cc,
        }
        if ir_dur < MIN_DURATION_S or ip_dur < MIN_DURATION_S:
            continue
        if nint < 1:
            continue
        out.append((sid, irtt_p, iperf_p, rec))
    return out


@dataclass
class SessionSlice:
    quantile: str
    quantile_q: float
    rank_index: int
    n_valid: int
    session_id: str
    start_utc: str
    irtt_relpath: str
    iperf_relpath: str
    csv_name: str
    overlap_s: float
    n_csv_rows: int
    n_irtt_good: int
    n_irtt_lost: int
    native_irtt_p50_ms: float
    native_irtt_p95_ms: float
    native_irtt_p99_ms: float
    native_irtt_max_ms: float
    native_oracle_cubic_gp_mbps: float
    mean_cubic_goodput_mbps: float
    sender_tcp_congestion: str
    receiver_tcp_congestion: str
    resample: str
    sqm: str
    capacity_meaning: str


def resample_session(sid: str, irtt_p: Path, iperf_p: Path) -> tuple[list[tuple], dict]:
    with irtt_p.open(encoding="utf-8") as f:
        irtt = json.load(f)
    with iperf_p.open(encoding="utf-8") as f:
        iperf = json.load(f)

    rtt_pts: list[tuple[float, float]] = []  # (abs_s, rtt_ms)
    n_lost = 0
    for rt in irtt.get("round_trips") or []:
        lost = str(rt.get("lost", "false")).strip().lower()
        if lost not in LOST_OK:
            n_lost += 1
            continue
        delay = rt.get("delay") or {}
        rtt_ns = delay.get("rtt")
        if rtt_ns is None:
            n_lost += 1
            continue
        try:
            wall_ns = rt["timestamps"]["client"]["send"]["wall"]
        except (KeyError, TypeError):
            n_lost += 1
            continue
        rtt_pts.append((float(wall_ns) / 1e9, float(rtt_ns) / 1e6))
    if not rtt_pts:
        raise ValueError(f"{sid}: no non-lost IRTT RTT samples")
    rtt_pts.sort(key=lambda x: x[0])

    ts = (iperf.get("start") or {}).get("timestamp") or {}
    ip_start = ts.get("timesecs")
    if ip_start is None:
        raise ValueError(f"{sid}: iperf missing start.timestamp.timesecs")
    ip_start = float(ip_start)
    cap_iv: list[tuple[float, float, float]] = []  # start, end, mbps
    weighted_bits = 0.0
    weighted_s = 0.0
    mbps_list: list[float] = []
    for iv in iperf.get("intervals") or []:
        sm = iv.get("sum") or {}
        st = ip_start + float(sm.get("start") or 0.0)
        en = ip_start + float(sm.get("end") or 0.0)
        bps = float(sm.get("bits_per_second") or 0.0)
        sec = float(sm.get("seconds") or max(en - st, 0.0))
        mbps = bps / 1e6
        cap_iv.append((st, en, mbps))
        weighted_bits += bps * sec
        weighted_s += sec
        mbps_list.append(mbps)
    if not cap_iv:
        raise ValueError(f"{sid}: no iperf intervals")
    cap_iv.sort(key=lambda x: x[0])

    native_oracle = (weighted_bits / max(weighted_s, 1e-9)) / 1e6
    rtts = [r for _, r in rtt_pts]

    t0 = max(rtt_pts[0][0], cap_iv[0][0])
    t1 = min(rtt_pts[-1][0], cap_iv[-1][1])
    overlap = t1 - t0
    if overlap < MIN_DURATION_S:
        raise ValueError(f"{sid}: overlap {overlap:.3f}s < {MIN_DURATION_S}")

    # Hold-within-bin capacity (100 ms iperf) + last-observation RTT (10 ms IRTT).
    ri = 0
    ci = 0
    last_rtt = rtt_pts[0][1]
    rows = []
    n_steps = int(overlap / DT_S)
    for k in range(n_steps):
        t_rel = k * DT_S
        t_abs = t0 + t_rel
        while ri + 1 < len(rtt_pts) and rtt_pts[ri + 1][0] <= t_abs + 1e-12:
            ri += 1
            last_rtt = rtt_pts[ri][1]
        if rtt_pts[ri][0] <= t_abs + 1e-12:
            last_rtt = rtt_pts[ri][1]
        while ci + 1 < len(cap_iv) and cap_iv[ci][1] <= t_abs + 1e-12:
            ci += 1
        st, en, mbps = cap_iv[ci]
        if t_abs + 1e-12 < st:
            mbps = cap_iv[0][2]
        rows.append((t_rel, last_rtt, mbps))

    end = iperf.get("end") or {}
    meta = {
        "overlap_s": overlap,
        "n_csv_rows": len(rows),
        "n_irtt_good": len(rtt_pts),
        "n_irtt_lost": n_lost,
        "native_irtt_p50_ms": _pct(rtts, 50),
        "native_irtt_p95_ms": _pct(rtts, 95),
        "native_irtt_p99_ms": _pct(rtts, 99),
        "native_irtt_max_ms": max(rtts),
        "native_oracle_cubic_gp_mbps": native_oracle,
        "mean_cubic_goodput_mbps": sum(mbps_list) / len(mbps_list),
        "sender_tcp_congestion": str(end.get("sender_tcp_congestion") or ""),
        "receiver_tcp_congestion": str(end.get("receiver_tcp_congestion") or ""),
        "t0_unix_s": t0,
        "t1_unix_s": t1,
    }
    return rows, meta


def write_csv(path: Path, rows: list[tuple]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(
            [
                "t_s",
                "rtt_ms",
                "capacity_mbps",
                "cubic_goodput_mbps",
                "loss_p",
                "reconfig",
            ]
        )
        for t_rel, rtt_ms, mbps in rows:
            w.writerow(
                [
                    f"{t_rel:.4f}",
                    f"{rtt_ms:.3f}",
                    f"{mbps:.4f}",
                    f"{mbps:.4f}",
                    f"{0.0:.6f}",
                    0,
                ]
            )


def write_manifest(out_dir: Path, slices: list[SessionSlice], n_pairs: int, n_valid: int) -> None:
    lines = [
        "# zhao_zenodo23 — vendored replay slices",
        "",
        "Research-era Starlink access traces. **Not** a product lock. **Do not merge**",
        "into Current / paid copy. **Do not mix** with `wetlinks_v1` or synthetic",
        "`starlink_v1` scorecards.",
        "",
        "## Citation (required)",
        "",
        "Dataset:",
        "",
        "- Zhao, Jinwei; Pan, Jianping (2023). *Starlink Latency and Downlink Throughput Measurement Dataset* (v20230917).",
        "- Zenodo DOI: [10.5281/zenodo.10020034](https://doi.org/10.5281/zenodo.10020034)",
        "- Record: https://zenodo.org/records/10020034",
        "- License: [CC-BY-4.0](https://creativecommons.org/licenses/by/4.0/)",
        "",
        "Paper:",
        "",
        "- Pan, Jianping; Zhao, Jinwei; Cai, Lin. *Measuring a Low-Earth-Orbit Satellite Network*.",
        "- IEEE PIMRC 2023. Preprint: https://arxiv.org/abs/2307.06863",
        "- Paper DOI: [10.1109/PIMRC56721.2023.10294034](https://doi.org/10.1109/PIMRC56721.2023.10294034)",
        "",
        "## What was measured (upstream README, not our claims)",
        "",
        "- Victoria, BC Ethernet dish → Seattle PoP → GCP `us-west1-a`.",
        "- Concurrent IRTT (UDP, 10 ms) + iPerf3 (TCP Cubic, `-R` downlink, 100 ms reports).",
        "- 120 s sessions every 10 min, 2023-09-13 through 2023-09-17 UTC.",
        "- Client and VM NTP via Google Public NTP.",
        "- **SQM / CAKE: unknown.** Upstream README does not confirm SQM on this dump.",
        "- Capacity column is **TCP Cubic downlink goodput**, not UDP saturation and not dish PHY / RF Mbps.",
        "- Oracle = time-integral of that cubic-goodput series = **lower bound** on path capacity.",
        "",
        "## Validity filter",
        "",
        f"- Complete IRTT + iperf3 JSON pair (identical filename timestamp). Indexed pairs: **{n_pairs}**.",
        f"- Duration ≥ {MIN_DURATION_S:.0f} s on both IRTT `stats.duration` and iperf3 `end.sum_received.seconds`.",
        f"- Valid after filter: **{n_valid}** (all indexed pairs passed on this dump).",
        "- Not cherry-picks. Not a single session.",
        "",
        "## Quantile rule (calendar, by session start time)",
        "",
        "Sort valid sessions by UTC start timestamp parsed from the filename",
        "(`YYYY-MM-DD-HH-MM-SS`, which matches iperf3 `start.timestamp` GMT).",
        "Pick five nearest-rank indices at q ∈ {0, 0.25, 0.50, 0.75, 1.00}:",
        "",
        "```",
        "idx = min(n - 1, int(q * (n - 1) + 0.5))   # round-half-up",
        "```",
        "",
        "This is a **calendar** sample of the campaign, not a goodput-quantile sample.",
        "We did **not** select by mean cubic goodput.",
        "",
        "## Resample",
        "",
        f"- Replay grid `dt = {DT_S:.2f}` s.",
        "- IRTT RTT: last non-lost sample with send-wall ≤ t (10 ms → 50 ms ZOH). Lost IRTT probes are skipped, not interpolated.",
        "- iPerf3 cubic goodput: **hold-within-bin** of the 100 ms interval containing t (each 100 ms value covers two 50 ms slots).",
        "- `capacity_mbps` == `cubic_goodput_mbps` by construction. Do not read this as dish PHY.",
        "- `loss_p = 0` (IRTT UDP loss is not a labeled bottleneck-loss process for the TCP series).",
        "- `reconfig = 0` always: **no invented handover flags** from TCP dips. Upstream dump does not label HOs.",
        "",
        "## JSON fields used (inspected, not hypothesized)",
        "",
        "- IRTT: `round_trips[].delay.rtt` (ns), `round_trips[].lost` (string), `round_trips[].timestamps.client.send.wall` (ns), `stats.duration` (ns).",
        "- iPerf3: `intervals[].sum.bits_per_second`, `intervals[].sum.start`/`end`, `start.timestamp.timesecs`, `end.sum_received.seconds`, `end.sender_tcp_congestion` (cubic on all 716).",
        "",
        "## Vendored sessions",
        "",
        "| q | idx | session_id | start UTC | csv | overlap s | native IRTT p95 ms | native cubic-gp oracle Mbps |",
        "|--:|----:|------------|-----------|-----|----------:|-------------------:|----------------------------:|",
    ]
    for s in slices:
        lines.append(
            f"| {s.quantile} | {s.rank_index} | `{s.session_id}` | {s.start_utc} | `{s.csv_name}` "
            f"| {s.overlap_s:.3f} | {s.native_irtt_p95_ms:.2f} | {s.native_oracle_cubic_gp_mbps:.2f} |"
        )
    lines += [
        "",
        "Source relative paths inside the decompressed dump:",
        "",
    ]
    for s in slices:
        lines.append(f"- `{s.session_id}`: `{s.irtt_relpath}` + `{s.iperf_relpath}`")
    lines += [
        "",
        "The ~1.17 GB `data-20230913-20230917.tar.zst` / ~9.7 GB `data/` tree is **not** vendored.",
        "",
        "## Reproduce slices",
        "",
        "```bash",
        "curl -L -o /tmp/data-20230913-20230917.tar.zst \\",
        "  'https://zenodo.org/records/10020034/files/data-20230913-20230917.tar.zst?download=1'",
        "mkdir -p /tmp/zhao_zenodo23/extract && tar -xf /tmp/data-20230913-20230917.tar.zst -C /tmp/zhao_zenodo23/extract",
        "python -m experiments.zhao_zenodo23_ingest --extract-dir /tmp/zhao_zenodo23/extract",
        "python -m experiments.zhao_zenodo23_geometry",
        "```",
        "",
    ]
    (out_dir / "MANIFEST.md").write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--extract-dir", type=Path, required=True)
    ap.add_argument("--out", type=Path, default=ROOT / "traces" / "zhao_zenodo23")
    args = ap.parse_args()
    extract_dir = args.extract_dir.resolve()
    out_dir = args.out if args.out.is_absolute() else (ROOT / args.out)
    out_dir = out_dir.resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    pairs = index_pairs(extract_dir)
    print(f"indexed pairs: {len(pairs)}", flush=True)
    valid = valid_pairs(pairs)
    print(f"valid (≥{MIN_DURATION_S:.0f}s IRTT+iperf): {len(valid)}", flush=True)
    if len(valid) < 5:
        raise SystemExit("need ≥5 valid sessions; refusing to invent traces")

    n = len(valid)
    chosen: list[SessionSlice] = []
    used_idx: set[int] = set()
    for q in QUANTILES:
        idx = nearest_rank_index(n, q)
        # If rounding collides, step to nearest unused (should not happen for 5 of 716).
        if idx in used_idx:
            for d in range(1, n):
                for cand in (idx + d, idx - d):
                    if 0 <= cand < n and cand not in used_idx:
                        idx = cand
                        break
                else:
                    continue
                break
        used_idx.add(idx)
        sid, irtt_p, iperf_p, rec = valid[idx]
        qlabel = f"q{int(q * 100):02d}"
        start = parse_session_id(sid)
        csv_name = f"{qlabel}_{start.strftime('%Y%m%dT%H%M%SZ')}.csv"
        print(f"slice {qlabel} idx={idx} {sid} ...", flush=True)
        rows, meta = resample_session(sid, irtt_p, iperf_p)
        write_csv(out_dir / csv_name, rows)
        try:
            irtt_rel = str(irtt_p.relative_to(extract_dir))
            iperf_rel = str(iperf_p.relative_to(extract_dir))
        except ValueError:
            irtt_rel = str(irtt_p)
            iperf_rel = str(iperf_p)
        sl = SessionSlice(
            quantile=qlabel,
            quantile_q=q,
            rank_index=idx,
            n_valid=n,
            session_id=sid,
            start_utc=start.strftime("%Y-%m-%dT%H:%M:%SZ"),
            irtt_relpath=irtt_rel,
            iperf_relpath=iperf_rel,
            csv_name=csv_name,
            overlap_s=meta["overlap_s"],
            n_csv_rows=meta["n_csv_rows"],
            n_irtt_good=meta["n_irtt_good"],
            n_irtt_lost=meta["n_irtt_lost"],
            native_irtt_p50_ms=meta["native_irtt_p50_ms"],
            native_irtt_p95_ms=meta["native_irtt_p95_ms"],
            native_irtt_p99_ms=meta["native_irtt_p99_ms"],
            native_irtt_max_ms=meta["native_irtt_max_ms"],
            native_oracle_cubic_gp_mbps=meta["native_oracle_cubic_gp_mbps"],
            mean_cubic_goodput_mbps=meta["mean_cubic_goodput_mbps"],
            sender_tcp_congestion=meta["sender_tcp_congestion"] or rec["sender_tcp_congestion"],
            receiver_tcp_congestion=meta["receiver_tcp_congestion"] or rec["receiver_tcp_congestion"],
            resample=f"dt={DT_S} IRTT last-obs (10ms) iperf hold-within-bin (100ms)",
            sqm="unknown (upstream README does not confirm CAKE/SQM)",
            capacity_meaning="TCP Cubic downlink goodput (iperf3 -R); lower bound on path capacity; not dish PHY",
        )
        chosen.append(sl)

    stats = {
        "era": "zhao_zenodo23",
        "doi": "10.5281/zenodo.10020034",
        "license": "CC-BY-4.0",
        "paper": "https://arxiv.org/abs/2307.06863",
        "quantile_rule": "calendar start-time nearest-rank q in {0,0.25,0.50,0.75,1} among valid pairs; idx=min(n-1,int(q*(n-1)+0.5))",
        "n_indexed_pairs": len(pairs),
        "n_valid": n,
        "min_duration_s": MIN_DURATION_S,
        "dt_s": DT_S,
        "sqm": "unknown",
        "sessions": [asdict(s) for s in chosen],
    }
    (out_dir / "session_stats.json").write_text(json.dumps(stats, indent=2) + "\n", encoding="utf-8")
    write_manifest(out_dir, chosen, len(pairs), n)
    print(f"wrote {out_dir}", flush=True)


if __name__ == "__main__":
    main()
