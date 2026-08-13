# Trace replay and ASCENT freeze windows

## CSV format

```csv
t_s,rtt_ms,capacity_mbps,loss_p,reconfig
0.00,40.0,80.0,0.0005,0
12.05,95.2,45.0,0.08,1
```

- `t_s`: time (seconds)
- `rtt_ms` or `rtt_s`
- `capacity_mbps` or `capacity_bps` (alias: `cubic_goodput_mbps`)
- optional `loss_p`, `reconfig` (0/1)

Load via `LeoPathConfig(trace_csv="traces/....csv", dt_s=0.05)`.

### Research era `zhao_zenodo23` (not a product lock)

Five calendar-quantile slices under `traces/zhao_zenodo23/` from Zhao/Pan Zenodo DOI [10.5281/zenodo.10020034](https://doi.org/10.5281/zenodo.10020034) (CC-BY-4.0); paper [arXiv:2307.06863](https://arxiv.org/abs/2307.06863). `capacity_mbps` **is** TCP Cubic downlink goodput (`cubic_goodput_mbps` duplicated so the meaning is not silently renamed). Oracle = ∫ that series = **lower bound** on path capacity. SQM unknown. No invented HO flags (`reconfig=0`). Geometry: `docs/leoaware_v312_zhao_zenodo23.md`. Do not mix with `wetlinks_v1` or synthetic `starlink_v1` scorecards. Do not merge.

Generate synthetic Starlink-class traces:

```bash
python -c "from leo_cc.network import generate_synthetic_starlink_trace; generate_synthetic_starlink_trace('traces/demo.csv', seed=13)"
python -c "from leo_cc.network import generate_synthetic_starlink_trace; generate_synthetic_starlink_trace('traces/starlink_v1_seed13.csv', seed=13, path_profile='starlink_v1')"
python -m experiments.run_trace_suite
```

`LeoPathConfig.path_profile` (generative, not CSV):

| Value | Role |
|-------|------|
| `ope_v36` (default) | Frozen v3.6/v3.7 path. Suite lock. Absolute 75/138.8 infeasible (see v3.8 Step 0). |
| `starlink_rtt` | Opt-in: cruise RTT 40–75 ms; HO spike only in the loss window. Same 20–120 Mbps band. |
| `starlink_v1` | Opt-in: `starlink_rtt` + 40–150 Mbps cap band. Not the product lock. |

Do not change the suite default without a Jon gate decision. Spec: `docs/leoaware_v38_capacity_model.md`.

## ASCENT freeze hints

`PathState` exposes:

- `freeze_active` / `freeze_remaining_s` - pre/post handover freeze (lead + trail)
- `next_capacity_bps` - predicted post-hop capacity when known
- `reconfigured` + `capacity_bps` + `rtt_s` + `epoch`

`LeoAwareCCA(use_path_hints=True)`:

1. During freeze: hold (minimal growth) - SaTCP-like soft freeze
2. **v3.1:** if `next_capacity_bps` is known, pre-position pacing toward the next path
3. On freeze end or reconfig: two-phase REPROBE with predicted capacity
4. Without hints: full endpoint detection (default, fair suite)

Generative paths use `LeoPath._peek_next_path()` (non-consuming RNG) so freeze-lead
capacity matches the upcoming hop without changing multi-seed path identity.

## ASCENT-D wire path (v3.2)

Simulator `path_hint_mode`:

| Mode | Behavior |
|------|----------|
| `direct` | Call `on_path_hint` from PathState (default, backward compatible) |
| `ascent_d` | Encode PATHHINT as ASCENT-D P9; decode with erase-on-fail |
| `ascent_plain` | Unprotected greppable ASCII unit |
| `none` | No path hints (endpoint-only) |

Optional `ascent_bit_flips=N` corrupts frames for integrity tests. Erased frames must not change rate.

```python
from leo_cc.ascent_path_hint import encode_path_hint_ascent_d, ingest_path_hint_stream
from leo_cc.ccas import LeoAwareCCA

cca = LeoAwareCCA(use_path_hints=True)
frame = encode_path_hint_ascent_d(reconfigured=True, capacity_bps=80e6, epoch=2, role="pilot")
ingest_path_hint_stream(cca, frame, now=1.0)
```

## OrbCC hybrid (optional, v3.2)

`use_orb_telemetry=True` injects synthetic pathID / qLen / bw. `LeoAwareCCA(use_orb_signals=True)` uses pathID for high-confidence REPROBE and empty qLen for mobility taxonomy. Full programmable-switch deployment is **not** assumed. Design + ablation: `docs/ascent_d_orbcc_hybrid.md`.
## fair_mode

`LeoAwareCCA(fair_mode=True)`:

- Lower BW percentile (70th)
- Tighter BDP target (~1.02x)
- Stronger delay yield for multi-flow coexistence

Measured seed 17 multi (3 flows): Jain ~0.61 default vs ~0.75 fair_mode.
