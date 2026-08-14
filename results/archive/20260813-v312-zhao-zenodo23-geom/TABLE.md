# zhao_zenodo23 geometry (no CCA)

Oracle cubic-goodput mean **30.37** Mbps → **INCONCLUSIVE** (cubic-goodput oracle mean < 75; this is a TCP Cubic lower bound on path capacity, not a FAIL).
IRTT p95 mean **146.74** ms → **FAIL** (bar ≤ 138.8).
Dual-gate: **INCONCLUSIVE on gp (lower bound); p95=FAIL**.

SQM unknown. Capacity is TCP Cubic downlink goodput (lower bound), not dish PHY.
No Crest / BBR / CUBIC sim on this cook. Do not merge. Do not mix with wetlinks_v1 or starlink_v1 82.09/76.26.

| q | session_id | start UTC | oracle cubic-gp Mbps | IRTT p95 ms | resampled oracle | resampled path p95 |
|---|------------|-----------|---------------------:|------------:|-----------------:|-------------------:|
| q00 | `2023-09-13-00-40-00` | 2023-09-13T00:40:00Z | 36.00 | 54.23 | 36.08 | 54.72 |
| q25 | `2023-09-14-06-30-00` | 2023-09-14T06:30:00Z | 38.16 | 64.20 | 38.21 | 64.44 |
| q50 | `2023-09-15-12-20-00` | 2023-09-15T12:20:00Z | 36.43 | 395.35 | 36.49 | 419.67 |
| q75 | `2023-09-16-18-00-00` | 2023-09-16T18:00:00Z | 28.16 | 81.55 | 28.24 | 82.83 |
| q100 | `2023-09-17-23-50-00` | 2023-09-17T23:50:00Z | 13.11 | 138.37 | 13.05 | 141.30 |
| **mean** | | | **30.37** | **146.74** | **30.41** | **152.59** |

