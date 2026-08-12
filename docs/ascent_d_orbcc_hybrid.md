# LeoAware v3.2: ASCENT-D integrity + OrbCC hybrid

**Date:** 2026-08-11  
**Scope:** Research prototype (`leo-aware-transport` / OrbitStack). Not production QUIC. Not affiliated with SpaceX / Cloudflare / X.

## Current-state analysis (pre-v3.2)

### Strengths already present (v3.1)

| Area | Implementation |
|------|----------------|
| Multi-signal reconfig detection | RTT MAD/z-score, ACK inter-arrival, rate collapse, loss burst (`_detect_reconfig`) |
| Soft REPROBE | ~0.55-0.62x cut, two-phase explore/fill, sample invalidation |
| Mobility vs congestion | Non-congestive loss does not CUBIC-collapse |
| Path hints | `on_path_hint` + freeze / next_capacity / epoch |
| Simulator | Slot-based `LeoPath` + multi-flow buffer, freeze lead peek |
| Extractable interface | `on_ack` / `on_loss` / `can_send` / `on_path_hint` / `on_ecn` |

### Gaps addressed in v3.2

1. **ASCENT integration was structural, not wire-level.** Simulator called `on_path_hint` with Python kwargs. No ASCENT unit, no ASCENT-D outer frame, no erase-on-fail.
2. **No integrity gate.** A corrupted control unit could have been applied if ever decoded loosely.
3. **No OrbCC exploration surface.** No pathID / utilization injection or consumer.
4. **No ablation harness** for endpoint vs ASCENT vs ASCENT-D vs Orb vs hybrid.

## Design: ASCENT-D path-hint channel

### Modules

| Module | Role |
|--------|------|
| `leo_cc/ascent_d.py` | Vendored P9 codec: RS(255,223), CRC-32C (or lab CRC-32), erase-on-fail |
| `leo_cc/ascent_path_hint.py` | PATHHINT unit encode/parse, ASCENT-D wrap, stream ingest, bit-flip noise |
| `leo_cc/sim.py` | `path_hint_mode`: `direct` \| `ascent_d` \| `ascent_plain` \| `none` |

### Inner unit (sacred-ASCII, greppable)

```
ASCENT/1.0
ROLE:pilot
PATHHINT reconfig=1 epoch=3 cap_bps=80000000 rtt_s=0.045000 freeze_s=0.120000 freeze_active=1 next_cap_bps=70000000
```

All bytes `< 0x80`.

### Outer: ASCENT-D P9

- Sync `D5 E5 C0 DE`, profile `0x44`, family RS(255,223)
- CRC over `profile || ecc_hdr || len || unit`
- **Fail policy:** parity/CRC/illegal profile/family/len => **erase unit**. No soft decode. Never call `on_path_hint` on erase.

### Ingest rails

- Trusted roles default: `pilot`, `gateway`
- Role reject does not apply
- Fallback: with `path_hint_mode=none` or `use_path_hints=False`, LeoAware stays endpoint-only and must still meet suite gates

### Emit cadence

ASCENT-D frames are emitted on **reconfig and freeze edges** only (not every 10 ms slot). Full RS encode every slot is too expensive for the research harness and is unnecessary once `freeze_until` is set.

## Design: OrbCC hybrid (optional)

### Modules

| Module | Role |
|--------|------|
| `leo_cc/orb_signals.py` | `OrbSignal`, utilization helper, synthetic `InNetworkTelemetry` |
| `LeoAwareCCA.on_orb_signal` | Consumer when `use_orb_signals=True` |

### What we take from OrbCC (arXiv:2508.19067)

- **pathID change** => high-confidence reconfig (confidence 0.95 REPROBE)
- **Low qLen + loss** => mobility taxonomy (not congestive cut)
- **Utilization** used only for mild MD when U is clearly over target **and** queue is non-trivial

### What we deliberately do *not* copy blindly

- Continuous AIMD every slot (over-controls this educational sim; regressed terrestrial in first ablation)
- Packet loss as non-signal (we still need endpoint taxonomy when Orb is off)

### Deployment realism

Full OrbCC needs programmable switches on path (or a gateway assist). Hybrid **degrades gracefully** when `use_orb_signals=False`.

## Confidence-conditioned REPROBE

| Source | Confidence | Cut bias |
|--------|------------|----------|
| Endpoint fusion | ~0.45-0.85 from score | stronger soft cut |
| ASCENT / path hint | 0.90 | milder cut + capacity seed |
| Orb pathID | 0.95 | mildest cut + capacity seed |

Higher confidence shortens explore phase slightly and seeds `bw_est` from predicted capacity when available.

## Ablation matrix

```bash
python -m experiments.test_ascent_d_integrity
python -m experiments.run_ablation --fast --seeds 13,7
# full: python -m experiments.run_ablation --seeds 13,7,42,99,123
```

Variants: `endpoint`, `ascent_plain`, `ascent_d`, `ascent_d_noisy`, `orb`, `hybrid`, `bbr`, `cubic`.

### Integrity gate (mandatory)

`ascent_d_noisy` with heavy bit flips: **applied == 0**, metrics match **endpoint** (erased frames produce zero rate change).

### First measured sweep (fast, seeds 13+7, post Orb soft-MD)

See `results/ablation/ablation_summary.csv` after re-run. Qualitative from first integrity-correct run:

- **ASCENT-D erase-on-fail proven:** noisy applied=0, erased>0, goodput identical to endpoint
- **ASCENT-D clean:** latency help on `leo_fast_ho` (p95 down vs endpoint on seed 13); goodput lift on `leo_single` mean
- **Terrestrial:** endpoint / ASCENT-D flat vs each other; BBR still slightly higher goodput
- **Orb continuous AIMD (v1 hybrid):** rejected after ablation (terrestrial collapse) -> soft MD only

## Reproduce

```bash
pip install -r requirements.txt
python -m experiments.test_ascent_d_integrity
python -m experiments.run_suite
python -m experiments.run_ablation --seeds 13,7,42
```

## quiche surface sketch

| Event | Call |
|-------|------|
| ACK | `on_ack(now, rtt, bytes)` |
| Loss | `on_loss(now, bytes, congestive=...)` |
| ASCENT-D side channel / DATAGRAM | `ingest_path_hint_stream(cca, bytes, now)` |
| In-network echo (if any) | `on_orb_signal(now, OrbSignal(...))` |
| Send | `min(can_send(now), pacing_budget)` |

## Honesty rails

- Slot sim is not ns-3 / real Starlink.
- BBRv3approx is educational, not bit-exact.
- OrbCC hybrid is a research exploration path, not a claim of switch deployment.
- ASCENT sacred-ASCII + erase-on-fail is normative for control units in this tree.
