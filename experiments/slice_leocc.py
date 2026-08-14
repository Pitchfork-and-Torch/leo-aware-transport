#!/usr/bin/env python3
"""Slice LeoCC / LeoReplayer traces → 5 downlink 90s replay CSVs.

Research era `leocc_v1` only. Not a product lock. Does not invent traces.

Source (MIT):
  Lai et al., LeoCC, ACM SIGCOMM 2025.
  https://github.com/SpaceNetLab/LeoCC
  Traces: https://cloud.tsinghua.edu.cn/d/9fc6fd096e764f57bd25/  (4.8K.zip)

Each published trace is ~120 s of concurrent:
  - heavy UDP iperf3 saturation → mahimahi-style bw_*.txt (12 Mbps / line)
  - light ICMP ping → delay_*.txt (one-way delay, 10 ms bins)

This slicer vendors **downlink only** (matches WetLinks download / Zhao -R).
Uplink dirs exist in the zip and are counted, not sliced.

Quantile rule (stated before looking at gp/p95): sort the 2400 downlink
traces by (site A..D, trace_no 1..600) and take nearest-rank
q ∈ {0, 0.25, 0.50, 0.75, 1}. Not cherry-picks.

Usage:
  python -m experiments.slice_leocc --zip /tmp/leocc/4.8K.zip
"""
from __future__ import annotations

import argparse
import csv
import json
import math
import sys
import zipfile
from dataclasses import asdict, dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

ERA = "leocc_v1"
SITES = ("A", "B", "C", "D")
TRACES_PER_SITE = 600
DURATION_S = 90.0
NATIVE_HINT_S = 120.0
DT_S = 0.05
DELAY_BIN_S = 0.01
BW_UNIT_MBPS = 12.0
QUANTILES = (0.0, 0.25, 0.50, 0.75, 1.0)
# LeoReplayer empirical downlink loss (not a labeled HO process).
DOWNLINK_LOSS_P = 0.0001
MIN_DELAY_BINS = int(DURATION_S / DELAY_BIN_S)  # 9000
OUT_DIR = ROOT / "traces" / "leocc"
DEFAULT_ZIP = Path("/tmp/leocc/4.8K.zip")
SHARE_URL = "https://cloud.tsinghua.edu.cn/d/9fc6fd096e764f57bd25/"
REPO_URL = "https://github.com/SpaceNetLab/LeoCC"
PAPER = "https://doi.org/10.1145/3718958.3750491"


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
    if n <= 0:
        raise ValueError("empty list")
    return min(n - 1, int(q * (n - 1) + 0.5))


def dir_name(site: str) -> str:
    return f"Anonymous_{site}_downlink"


def zip_members(site: str, n: int) -> tuple[str, str]:
    d = f"{dir_name(site)}/{n}"
    return f"{d}/bw_{n}.txt", f"{d}/delay_{n}.txt"


def catalog_downlink() -> list[tuple[str, int]]:
    return [(site, n) for site in SITES for n in range(1, TRACES_PER_SITE + 1)]


def parse_delay_owd_ms(text: str) -> list[float]:
    out: list[float] = []
    for line in text.splitlines():
        s = line.strip()
        if not s:
            continue
        out.append(float(s))
    return out


def parse_bw_mbps_per_ms(text: str) -> dict[int, float]:
    """Mahimahi / LeoReplayer: each line is a ms timestamp; +12 Mbps per line."""
    cap: dict[int, float] = {}
    for line in text.splitlines():
        s = line.strip()
        if not s:
            continue
        t = int(s)
        cap[t] = cap.get(t, 0.0) + BW_UNIT_MBPS
    return cap


def native_oracle_mbps(cap_ms: dict[int, float], duration_s: float) -> float:
    ms_end = int(duration_s * 1000.0)
    if ms_end <= 0:
        return 0.0
    total = 0.0
    for ms in range(ms_end):
        total += cap_ms.get(ms, 0.0)
    return total / ms_end


def resample_rows(
    delay_owd: list[float],
    cap_ms: dict[int, float],
    duration_s: float = DURATION_S,
    dt_s: float = DT_S,
) -> list[tuple[float, float, float, float]]:
    """50 ms grid: last-obs OWD, mean 1 ms UDP-sat capacity, RTT = 2×OWD."""
    n = int(duration_s / dt_s)
    ms_per_slot = int(round(dt_s * 1000.0))
    rows: list[tuple[float, float, float, float]] = []
    last_pos = next((x for x in delay_owd if x > 0.0), 1.0)
    for k in range(n):
        t_rel = k * dt_s
        di = min(int(t_rel / DELAY_BIN_S), len(delay_owd) - 1)
        owd = delay_owd[di]
        if owd > 0.0:
            last_pos = owd
        else:
            # Source sometimes writes 0 (stats min). Hold last positive OWD.
            # Do not invent a floor. One slot in A/600 on this dump.
            owd = last_pos
        rtt = 2.0 * owd
        ms0 = k * ms_per_slot
        acc = 0.0
        for ms in range(ms0, ms0 + ms_per_slot):
            acc += cap_ms.get(ms, 0.0)
        cap = acc / ms_per_slot
        rows.append((t_rel, rtt, owd, cap))
    return rows


@dataclass
class WindowSlice:
    quantile: str
    quantile_q: float
    rank_index: int
    n_valid: int
    site: str
    direction: str
    trace_no: int
    zip_bw: str
    zip_delay: str
    csv_name: str
    n_delay_bins: int
    n_csv_rows: int
    native_duration_s: float
    native_owd_p50_ms: float
    native_owd_p95_ms: float
    native_owd_p99_ms: float
    native_owd_max_ms: float
    native_rtt_p95_ms: float
    native_oracle_udp_mbps: float
    resampled_oracle_udp_mbps: float
    rtt_rule: str
    loss_p: float
    reconfig: int
    capacity_meaning: str


def write_csv(path: Path, rows: list[tuple[float, float, float, float]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(
            [
                "t_s",
                "rtt_ms",
                "owd_ms",
                "capacity_mbps",
                "udp_sat_mbps",
                "loss_p",
                "reconfig",
            ]
        )
        for t_rel, rtt, owd, cap in rows:
            w.writerow(
                [
                    f"{t_rel:.4f}",
                    f"{rtt:.3f}",
                    f"{owd:.3f}",
                    f"{cap:.4f}",
                    f"{cap:.4f}",
                    f"{DOWNLINK_LOSS_P:.6f}",
                    0,
                ]
            )


def write_manifest(out_dir: Path, slices: list[WindowSlice], n_zip: int, n_valid: int) -> None:
    lines = [
        "# leocc_v1 — vendored LeoCC downlink replay slices",
        "",
        "Research-era Starlink access traces. **Not** a product lock. **Do not merge**",
        "into Current / paid copy. **Do not mix** with `wetlinks_v1`, `zhao_zenodo23`,",
        "or synthetic `starlink_v1` Crest 82.09/76.26.",
        "",
        "## Citation (required)",
        "",
        "- Lai, Zeqi; Li, Zonglun; Wu, Qian; Li, Hewu; Li, Jihao; Xie, Xin; Li, Yuanjie; Liu, Jun; Wu, Jianping.",
        "  *LeoCC: Making Internet Congestion Control Robust to LEO Satellite Dynamics*.",
        "  ACM SIGCOMM 2025. DOI [10.1145/3718958.3750491](https://doi.org/10.1145/3718958.3750491).",
        f"- Code + recorder: {REPO_URL} (MIT).",
        f"- Traces: Tsinghua Cloud share {SHARE_URL} (`4.8K.zip`).",
        "",
        "## What was measured (upstream, not our claims)",
        "",
        "- Concurrent **heavy UDP** (iperf3 saturation) + **light ICMP** ping.",
        "- Each trace ~120 s. Four anonymous sites (A–D) × uplink/downlink × 600.",
        "- `bw_*.txt`: mahimahi timestamps; each repeated line = 12 Mbps at that millisecond.",
        "- `delay_*.txt`: one-way delay (ms) per 10 ms bin (LeoReplayer / traces README).",
        "- Capacity is **UDP saturation**, not TCP Cubic goodput, not dish PHY / RF Mbps.",
        "- ICMP rides a separate Starlink SQM queue (LeoReplayer README). Delay is **base**",
        "  path delay, not CCA-queued RTT. Soft-QIR still adds sojourn in our sim.",
        "",
        "## Direction filter (stated before looking at gp/p95)",
        "",
        "This era slices **downlink only** (4×600 = 2400), matching WetLinks download",
        "and Zhao `-R` downlink. Uplink dirs are present in the zip (counted below)",
        "and are a different bottleneck class (LeoReplayer: higher uplink loss,",
        "lower sat rate). We do **not** mix them into the five-window mean.",
        "",
        "## Validity filter",
        "",
        f"- Downlink pair `bw_N.txt` + `delay_N.txt` exists in the zip. Indexed: **{n_zip}**.",
        f"- Delay bins ≥ {MIN_DELAY_BINS} (native duration ≥ {DURATION_S:.0f} s).",
        f"- At least one positive 1 ms UDP-sat sample in [0, {DURATION_S:.0f} s).",
        f"- Valid after filter: **{n_valid}**.",
        "- Excluded short delay (not gp/p95): `D/16` (75.92 s), `D/212` (88.39 s) on this dump.",
        "- Not cherry-picks. Not a single pretty session.",
        "",
        "## Quantile rule (catalog order, not goodput)",
        "",
        "Sort valid downlink traces by `(site A..D, trace_no 1..600)`.",
        "Nearest-rank q ∈ {0, 0.25, 0.50, 0.75, 1.00}:",
        "",
        "```",
        "idx = min(n - 1, int(q * (n - 1) + 0.5))   # round-half-up",
        "```",
        "",
        "We did **not** select by mean UDP-sat or delay p95.",
        "",
        "## Resample / inferences",
        "",
        f"- Gate window: first **{DURATION_S:.0f} s** of each ~120 s trace (product duration).",
        f"- Replay grid `dt = {DT_S:.2f}` s.",
        "- OWD: last-obs of the 10 ms delay bin with start ≤ t.",
        "  Source 0 is replaced by the last positive OWD (do not invent a floor).",
        "- **`rtt_ms = 2 × owd_ms`**. traces/README + mahimahi `mm-delay` are one-way;",
        "  a packet sees the delay on both directions. Native OWD p95 is also archived.",
        "- Capacity: mean of the 50 one-millisecond UDP-sat samples in the slot.",
        f"- `loss_p = {DOWNLINK_LOSS_P}` (LeoReplayer empirical downlink). Not a HO series.",
        "- `reconfig = 0` always: **no invented handover flags**. Their extract script",
        "  is documented as unreliable on irregular traces; we do not run it.",
        "",
        "## Vendored windows",
        "",
        "| q | idx | site | trace | csv | native OWD p95 ms | 2×OWD p95 ms | native UDP-sat oracle Mbps |",
        "|--:|----:|------|------:|------|------------------:|-------------:|---------------------------:|",
    ]
    for s in slices:
        lines.append(
            f"| {s.quantile} | {s.rank_index} | {s.site} | {s.trace_no} | `{s.csv_name}` "
            f"| {s.native_owd_p95_ms:.2f} | {s.native_rtt_p95_ms:.2f} "
            f"| {s.native_oracle_udp_mbps:.2f} |"
        )
    lines += [
        "",
        "Zip members:",
        "",
    ]
    for s in slices:
        lines.append(f"- `{s.quantile}`: `{s.zip_bw}` + `{s.zip_delay}`")
    lines += [
        "",
        "The ~699 MB `4.8K.zip` / 4800-trace tree is **not** vendored.",
        "",
        "## Reproduce slices",
        "",
        "```bash",
        f"curl -L -o /tmp/leocc/4.8K.zip '{SHARE_URL}files/?p=/4.8K.zip&dl=1'",
        "python -m experiments.slice_leocc --zip /tmp/leocc/4.8K.zip",
        "python -m experiments.run_leocc --geometry-only",
        "```",
        "",
    ]
    (out_dir / "MANIFEST.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def index_valid(zf: zipfile.ZipFile) -> list[tuple[str, int]]:
    names = set(zf.namelist())
    valid: list[tuple[str, int]] = []
    for site, n in catalog_downlink():
        bw, delay = zip_members(site, n)
        if bw in names and delay in names:
            valid.append((site, n))
    return valid


def slice_one(
    zf: zipfile.ZipFile, site: str, n: int
) -> tuple[list[tuple[float, float, float, float]], dict]:
    bw_name, delay_name = zip_members(site, n)
    delay_owd = parse_delay_owd_ms(zf.read(delay_name).decode("utf-8"))
    if len(delay_owd) < MIN_DELAY_BINS:
        raise ValueError(f"{site}/{n}: delay bins {len(delay_owd)} < {MIN_DELAY_BINS}")
    cap_ms = parse_bw_mbps_per_ms(zf.read(bw_name).decode("utf-8"))
    oracle = native_oracle_mbps(cap_ms, DURATION_S)
    if oracle <= 0.0:
        raise ValueError(f"{site}/{n}: no positive UDP-sat in first {DURATION_S:.0f}s")
    owd90 = delay_owd[:MIN_DELAY_BINS]
    rows = resample_rows(delay_owd, cap_ms)
    resampled_oracle = sum(r[3] for r in rows) / max(len(rows), 1)
    meta = {
        "n_delay_bins": len(delay_owd),
        "native_duration_s": len(delay_owd) * DELAY_BIN_S,
        "native_owd_p50_ms": _pct(owd90, 50),
        "native_owd_p95_ms": _pct(owd90, 95),
        "native_owd_p99_ms": _pct(owd90, 99),
        "native_owd_max_ms": max(owd90),
        "native_rtt_p95_ms": 2.0 * _pct(owd90, 95),
        "native_oracle_udp_mbps": oracle,
        "resampled_oracle_udp_mbps": resampled_oracle,
        "zip_bw": bw_name,
        "zip_delay": delay_name,
    }
    return rows, meta


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--zip", type=Path, default=DEFAULT_ZIP)
    ap.add_argument("--out", type=Path, default=OUT_DIR)
    args = ap.parse_args()
    zpath = args.zip if args.zip.is_absolute() else (ROOT / args.zip)
    out_dir = args.out if args.out.is_absolute() else (ROOT / args.out)
    if not zpath.is_file():
        raise SystemExit(
            f"missing {zpath}\nDownload:\n"
            f"  mkdir -p /tmp/leocc && curl -L -o /tmp/leocc/4.8K.zip "
            f"'{SHARE_URL}files/?p=/4.8K.zip&dl=1'"
        )
    out_dir.mkdir(parents=True, exist_ok=True)

    with zipfile.ZipFile(zpath) as zf:
        n_zip = len(catalog_downlink())
        valid = index_valid(zf)
        print(f"downlink indexed pairs: {len(valid)} / {n_zip}", flush=True)
        # Duration filter without parsing 30 MB bw files: delay-only first.
        durable: list[tuple[str, int]] = []
        excluded_short: list[dict] = []
        for site, n in valid:
            _, delay_name = zip_members(site, n)
            raw = zf.read(delay_name)
            nlines = raw.count(b"\n") + (0 if raw.endswith(b"\n") or not raw else 1)
            if nlines >= MIN_DELAY_BINS:
                durable.append((site, n))
            else:
                excluded_short.append(
                    {
                        "site": site,
                        "trace_no": n,
                        "delay_bins": nlines,
                        "duration_s": nlines * DELAY_BIN_S,
                    }
                )
        print(f"valid delay≥{DURATION_S:.0f}s: {len(durable)}", flush=True)
        if excluded_short:
            print(f"excluded short delay: {excluded_short}", flush=True)
        if len(durable) < 5:
            raise SystemExit("need ≥5 valid downlink traces; refusing to invent")

        n = len(durable)
        chosen: list[WindowSlice] = []
        used: set[int] = set()
        for q in QUANTILES:
            idx = nearest_rank_index(n, q)
            if idx in used:
                for d in range(1, n):
                    for cand in (idx + d, idx - d):
                        if 0 <= cand < n and cand not in used:
                            idx = cand
                            break
                    else:
                        continue
                    break
            used.add(idx)
            site, trace_no = durable[idx]
            qlabel = f"q{int(q * 100):02d}"
            print(f"slice {qlabel} idx={idx} {site}_downlink/{trace_no} ...", flush=True)
            rows, meta = slice_one(zf, site, trace_no)
            csv_name = f"{qlabel}_{site}_downlink_{trace_no:03d}.csv"
            write_csv(out_dir / csv_name, rows)
            sl = WindowSlice(
                quantile=qlabel,
                quantile_q=q,
                rank_index=idx,
                n_valid=n,
                site=site,
                direction="downlink",
                trace_no=trace_no,
                zip_bw=meta["zip_bw"],
                zip_delay=meta["zip_delay"],
                csv_name=csv_name,
                n_delay_bins=meta["n_delay_bins"],
                n_csv_rows=len(rows),
                native_duration_s=meta["native_duration_s"],
                native_owd_p50_ms=meta["native_owd_p50_ms"],
                native_owd_p95_ms=meta["native_owd_p95_ms"],
                native_owd_p99_ms=meta["native_owd_p99_ms"],
                native_owd_max_ms=meta["native_owd_max_ms"],
                native_rtt_p95_ms=meta["native_rtt_p95_ms"],
                native_oracle_udp_mbps=meta["native_oracle_udp_mbps"],
                resampled_oracle_udp_mbps=meta["resampled_oracle_udp_mbps"],
                rtt_rule="rtt_ms = 2 * owd_ms (LeoReplayer one-way delay)",
                loss_p=DOWNLINK_LOSS_P,
                reconfig=0,
                capacity_meaning="UDP iperf3 saturation (mahimahi 12 Mbps/line); not dish PHY",
            )
            chosen.append(sl)
            print(
                f"  owd_p95={sl.native_owd_p95_ms:.2f}  rtt_p95={sl.native_rtt_p95_ms:.2f}  "
                f"oracle={sl.native_oracle_udp_mbps:.2f}",
                flush=True,
            )

    stats = {
        "era": ERA,
        "license": "MIT (SpaceNetLab/LeoCC)",
        "paper": PAPER,
        "repo": REPO_URL,
        "share": SHARE_URL,
        "zip_name": "4.8K.zip",
        "direction": "downlink_only",
        "quantile_rule": (
            "downlink catalog (site A..D, trace 1..600) nearest-rank "
            "q in {0,0.25,0.50,0.75,1}; idx=min(n-1,int(q*(n-1)+0.5))"
        ),
        "n_downlink_indexed": n_zip,
        "n_valid": n,
        "excluded_short_delay": excluded_short,
        "n_uplink_not_sliced": 4 * TRACES_PER_SITE,
        "min_duration_s": DURATION_S,
        "dt_s": DT_S,
        "rtt_rule": "2 * one-way delay",
        "loss_p": DOWNLINK_LOSS_P,
        "reconfig": 0,
        "sessions": [asdict(s) for s in chosen],
    }
    (out_dir / "session_stats.json").write_text(
        json.dumps(stats, indent=2) + "\n", encoding="utf-8"
    )
    write_manifest(out_dir, chosen, n_zip, n)
    print(f"wrote {out_dir}", flush=True)


if __name__ == "__main__":
    main()
