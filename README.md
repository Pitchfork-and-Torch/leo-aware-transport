# LeoAware Transport (OrbitStack)

**LEO-aware congestion control research prototype** for Starlink-class satellite paths.

**Product brief:** [orbitstack.jonbailey.xyz](https://orbitstack.jonbailey.xyz/)  
**Org:** [Pitchfork-and-Torch](https://github.com/Pitchfork-and-Torch) | **License:** MIT

Traditional congestion control assumes a **stable path and stable RTT**. LEO (Starlink-class) has neither. Bandwidth alone is insufficient; the transport stack needs LEO-aware innovation.

This repo is a **self-contained, runnable research prototype** (pure Python + numpy/matplotlib/pandas). Clone, run the suite, inspect numbers and plots. Sender modules are shaped so they can be adapted toward a QUIC congestion controller (e.g. quiche-class stacks).

**Not affiliated with X, Cloudflare, or SpaceX.** Educational BBR approx - not bit-exact production BBRv3.

![OrbitStack / ASCENT wire motif: LEO-aware adaptive path control](docs/assets/ascent-wire-motif.jpg)

*ASCENT-aware LEO control plane motif (OrbitStack product art).*

---

## Problem

LEO dynamics break core CCA assumptions (CUBIC, BBR family, etc.):

| Phenomenon | Effect on classic CCAs |
|------------|------------------------|
| Handovers / reconfigs every ~15-60s | Stale min-RTT and bandwidth samples |
| Abrupt RTT jumps (20-100+ ms base) | Wrong BDP; under- or over-send |
| Non-congestive loss bursts (beam/ISL) | CUBIC collapses; BBR may keep stale model |
| Capacity flicker | Under-utilization or excess queueing |

**Goal:** high goodput + controlled latency under LEO dynamics, with a **sender-side, QUIC-friendly** design (no hard dependency on in-network assist).

---

## Quick start

```bash
cd leo-aware-transport
pip install -r requirements.txt
python -m experiments.run_suite
python -m experiments.multi_seed
python -m experiments.run_trace_suite
```

Outputs land in `results/`:

- `summary.csv` / `summary.json` - metrics table
- `*_timeseries.png` - cwnd, goodput, RTT with handover markers
- `leo_single_throughput_latency.png` - Pareto scatter

Optional single-scenario demo:

```bash
python -m experiments.demo
```

---

## Architecture

```
leo_cc/
  network.py          # Starlink-class path dynamics (handover, RTT, capacity, loss)
  ccas.py             # CUBIC, BBRv3approx, LeoAware (extractable sender modules)
  sim.py              # Slot-based multi-flow transport simulator
  ascent_d.py         # ASCENT-D P9: RS(255,223) + erase-on-fail
  ascent_path_hint.py # PATHHINT units + fail-closed ingest
  orb_signals.py      # OrbCC-style synthetic telemetry (optional)
  metrics.py          # Goodput, RTT percentiles, loss, Jain fairness
  plotting.py         # Timeseries + throughput-latency figures
experiments/
  run_suite.py              # Full reproducible evaluation (endpoint default)
  run_ablation.py           # endpoint / ASCENT-D / Orb / hybrid matrix
  test_ascent_d_integrity.py
  demo.py
docs/
  architecture.md
  ascent_d_orbcc_hybrid.md
  related_work.md
  cloudflare_starlink_bridge.md
```

### Network model

`LeoPath` is a configurable discrete-time path (default 10 ms slots):

- Periodic + jittered handovers / connection reconfigurations
- Abrupt RTT and capacity redraws per epoch
- Non-congestive loss window correlated with reconfiguration
- Shared bottleneck buffer (overflow = congestive loss)
- Optional simplified ISL extra delay (`isl_enabled=True`)
- `terrestrial=True` for stable-path control experiments

Conceptual entities: **ground terminal -> LEO satellite -> (ISL) -> ground station**. The path object abstracts end-to-end delay and bottleneck capacity as seen by the sender.

### Congestion control

| Algorithm | Role |
|-----------|------|
| **CUBIC** | Loss-based baseline; treats mobility loss as congestion |
| **BBRv3approx** | Model-based baseline (educational BBR-family; not bit-exact BBRv3) |
| **LeoAware** | Novel LEO-aware CCA (default: endpoint-only detection) |

All implement a small sender-side interface (`on_ack`, `on_loss`, `can_send`, optional `on_path_hint`) so they can be ported toward a QUIC congestion controller.

---

## LeoAware design

### Endpoint reconfiguration detection

No perfect network cooperation required. Signals:

1. **RTT jump outliers** vs recent median / p25 (absolute and relative thresholds)
2. **ACK inter-arrival gaps** (path freeze during reconfig)
3. **Loss bursts without RTT inflation** (non-congestive mobility)

Optional `use_path_hints=True` accepts explicit reconfiguration signals (Starlink / edge assist path).
Optional `use_orb_signals=True` consumes OrbCC-style pathID / queue telemetry when the simulator injects it.

**ASCENT-D integrity (v3.2):** critical path hints can ride ASCENT-D P9 (RS(255,223) + CRC). Erase-on-fail: never act on a corrupted control unit. See `docs/ascent_d_orbcc_hybrid.md` and `python -m experiments.test_ascent_d_integrity`.

```bash
python -m experiments.test_ascent_d_integrity
python -m experiments.run_ablation --fast --seeds 13,7
```

### Reconfiguration-aware bottleneck model

On detected change:

1. Discard stale **min-RTT** and **bandwidth samples**
2. Enter **REPROBE**: soft cwnd cut (~0.55x), not CUBIC collapse
3. Rapid controlled growth, then cruise near ~1.08 x BDP from post-change samples

### Mobility vs congestion

| Signal | Action |
|--------|--------|
| Loss near reconfig or loss without RTT inflation | **Do not** collapse cwnd (`mobility_loss`) |
| Loss + elevated RTT / buffer overflow | Congestive recovery (~0.7x) |

This is the core distinction classic CUBIC lacks on LEO.

---

## Evaluation suite

Scenarios in `experiments/run_suite.py`:

1. **leo_single** - long-lived flow, ~22s handovers
2. **leo_fast_ho** - aggressive ~12s handovers
3. **leo_multi** - 3 competing flows (Jain fairness)
4. **terrestrial** - stable path control

Metrics: goodput, avg / p95 / p99 RTT, loss rate, utilization, Jain index, handover count.

### Primary objective: multi-seed `leo_fast_ho` (LeoAware v3.4-p95)

Seeds 13,7,42,99,123 · 90s · **endpoint-only** default (public suite).  
Public p95 gate: Leo p95 mean ≤ BBR p95 (138.8). Means only - do not market peaks.

| CCA | Goodput mean | p95 mean | Notes |
|-----|-------------:|---------:|-------|
| CUBIC | 5.47 | 124.8 | Collapses under mobility |
| BBRv3approx | 70.88 | 138.8 | Reference |
| **LeoAware v3.4-p95** | **73.57** | **138.37** | **gp > BBR; p95 under BBR** |
| LeoAware v3.3-A | 78.06 | 149.7 | higher gp / p95 residual (historical) |
| LeoAware v3.1 | 68.98 | 133.6 | earlier p95-under-BBR gate |

### Hybrid fuse ablation (fast, seeds 13+7)

| Variant | leo_fast_ho gp | p95 | Note |
|---------|---------------:|----:|------|
| endpoint | 84.04 | 123.9 | no assist |
| **hybrid** | **75.57** | **109.6** | ASCENT-D + Orb fuse; no double-cut |
| orb | 72.99 | 116.9 | pathID only |
| ascent_d_noisy | = endpoint | = endpoint | erase-on-fail proven |

Integrity: `python -m experiments.test_ascent_d_integrity` (green).

### Suite seed 13 snapshot (not the multi-seed optimize target)

| Scenario | CCA | Goodput Mbps | p95 RTT ms |
|----------|-----|-------------:|-----------:|
| leo_fast_ho | LeoAware | 63.36 | 146.9 |
| leo_single | LeoAware | 71.88 | 111.9 |
| terrestrial | LeoAware | 77.86 | 40.0 |

v3.4-p95 Current: delay-aware cruise / REPROBE fill ceilings (endpoint multi-seed p95 reclaim).  
v3.3-A rails retained: hybrid fuse (`_should_suppress_orb_reprobe`), ASCENT-D erase-on-fail, path-aware BDP.  
Log: `docs/experiment_log.md`. Design: `docs/leoaware_v33_hybrid_fuse.md`, `docs/ascent_d_orbcc_hybrid.md`.  
Archive: `results/archive/20260812-p95-reclaim/`.

Reproduce:

```bash
python -m experiments.test_ascent_d_integrity
python -m experiments.run_suite
python -m experiments.multi_seed
python -m experiments.run_ablation --fast --seeds 13,7
# inspect results/summary.csv and plots
```

---

## Collaboration bridge (Cloudflare x Starlink)

See `docs/cloudflare_starlink_bridge.md` for a fuller write-up. Short version:

1. **Endpoint-only first** - ship LeoAware-class logic in quiche / edge QUIC without waiting on satellite signaling.
2. **Optional path hints** - if Starlink exposes reconfig / ephemeris / beam-switch markers, feed `on_path_hint` for lower detection lag.
3. **Edge deployment** - Cloudflare PoPs terminating Starlink eyeball traffic are a natural A/B measurement surface.
4. **Multipath / ISL** - later: schedule across dual paths when multiple ground stations or ISL routes are visible.
5. **AI-scale traffic** - long-lived bulk + interactive flows both suffer from wrong BDP after hops; LEO-aware CC is infrastructure for reliable model training and inference over satellite.

---

## Limitations and next steps

- Packet-level fidelity is simplified (slot sim, not ns-3 / full QUIC state machine).
- BBRv3approx is educational, not a production BBR port.
- No real Starlink trace replay yet (hooks are ready for CSV RTT/capacity traces).
- Multipath is optional/simplified (ISL delay only).
- Not production-hardened (no pacing timer fidelity, ECN, or ACK aggregation).

Natural next steps: real measurement traces, quiche controller port, multipath, ML handover prediction, in-network assists (OrbCC-class), kernel/eBPF experiments.

---

## Related work

See `docs/related_work.md` for LeoCC, OrbCC, SaTCP / StarQUIC-style freezing, and how LeoAware sits relative to them.

---

## Links

| | |
|--|--|
| Product landing | https://orbitstack.jonbailey.xyz/ |
| ASCENT wire | https://ascent.jonbailey.xyz/ |
| Issues | Use GitHub Issues on this repo |

## License

MIT. See `LICENSE`. Copyright Pitchfork-and-Torch.

## Citation-style note

If you use this prototype in research or product exploration, please reference the problem framing (LEO breaks stable-path CCA assumptions) and this repository's LeoAware design (endpoint reconfiguration detection + sample invalidation + mobility-aware loss handling).
