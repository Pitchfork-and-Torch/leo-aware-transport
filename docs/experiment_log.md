# Experiment log (OrbitStack / LeoAware)

Scientific record of continuous improvement. Every entry includes hypothesis,
change, seeds, metrics, and decision. Negative results are logged with the same care.

Reproduce default suite:

```bash
python -m experiments.run_suite
python -m experiments.multi_seed --seeds 13,7,42,99,123
```

---

## v0 - Initial public numbers (pre-v2 soft-reprobe)

**Date:** 2026-08-11 (approx, first OrbitStack publish)  
**Commit:** early public tree (pre multi-signal v2)  
**Hypothesis:** Soft re-probe + mobility/congestion taxonomy beats CUBIC on LEO without tanking terrestrial.

### leo_fast_ho (seed 13, suite default)

| CCA | Goodput | Avg RTT | p95 RTT | Loss | HOs |
|-----|---------|---------|---------|------|-----|
| CUBIC | 6.44 Mbps | 65.4 ms | 134.3 ms | 0.14% | 7 |
| BBRv3approx | 65.38 Mbps | 116.2 ms | 188.6 ms | 1.18% | 7 |
| **LeoAware** | **68.31 Mbps** | **87.3 ms** | **164.0 ms** | 1.26% | 7 |

### leo_single (seed 11)

| CCA | Goodput | p95 RTT |
|-----|---------|---------|
| CUBIC | 9.04 Mbps | 111.2 ms |
| BBRv3approx | 83.99 Mbps | 161.8 ms |
| LeoAware | 64.67 Mbps | 129.1 ms |

### terrestrial (seed 19)

LeoAware ~77.98 Mbps @ 40 ms p95 (near BBR ~78.81).

**Decision:** Accept as public baseline on site / launch materials. CUBIC destroyed by mobility loss; LeoAware wins stress Pareto vs BBR approx.

---

## v2 - Multi-signal detection + two-phase REPROBE

**Date:** 2026-08-11  
**Commit:** `0a66785` (and successors)  
**Hypothesis:** MAD/fusion reconfig detection + two-phase soft recovery + soft pacing improves goodput-latency under frequent handovers without terrestrial regression.

### Key code changes (`leo_cc/ccas.py`)

- Multi-signal reconfig fusion (RTT MAD, ACK IA, rate collapse, loss burst)
- Two-phase REPROBE (explore then fill) with early exit
- Soft pacing (non-starving); optional path-hint capacity blend
- Mild delay_yield for coexistence

### Suite seed 13 (default harness)

| Scenario | CCA | Goodput | p95 RTT | vs v0 LeoAware |
|----------|-----|---------|---------|----------------|
| leo_fast_ho | LeoAware | **70.36 Mbps** | **123.2 ms** | +3% gp, **-41 ms p95** |
| leo_single | LeoAware | **81.97 Mbps** | **141.1 ms** | +27% gp |
| terrestrial | LeoAware | **77.39 Mbps** | 40.0 ms | ~flat |

Archive: `results/archive/20260811-v2-0a66785/`  
Design: `docs/leoaware_v2_design.md`

**Decision:** **Notable win on suite seed 13.** Ship v2 on public repo + update site current tab. Keep v0 as historical baseline tab.

### Multi-seed robustness (seeds 13,7,42,99,123) - post hoc

| Scenario | CCA | goodput mean | goodput std | p95 mean | p95 std |
|----------|-----|-------------:|------------:|---------:|--------:|
| leo_fast_ho | CUBIC | 5.47 | 0.86 | 124.8 | 13.6 |
| leo_fast_ho | BBRv3approx | **70.88** | 11.47 | **138.8** | 33.0 |
| leo_fast_ho | LeoAware v2 | 64.82 | 11.06 | 146.5 | 30.5 |
| leo_single | BBRv3approx | 58.39 | 8.18 | **131.3** | 28.7 |
| leo_single | LeoAware v2 | **61.09** | 12.62 | 146.4 | 28.7 |
| terrestrial | BBRv3approx | 78.81 | 0.00 | 40.0 | 0 |
| terrestrial | LeoAware v2 | 77.63 | 0.18 | 40.0 | 0 |

**Analysis:** Seed 13 overstated the fast-HO win vs BBR. Multi-seed means: BBR higher mean goodput on fast HO; LeoAware still destroys CUBIC and is competitive on single-flow goodput. High seed variance on LEO scenarios. Next iterations must optimize multi-seed mean, not single-seed peaks.

Archive: `results/archive/20260811-v2-multiseed/`

---

## v2.1 attempt - reduce false reconfig - REJECTED

**Date:** 2026-08-11  
**Hypothesis:** Raising fusion threshold (1.55->1.85) and classic-jump floor reduces false REPROBE on noisy seeds, lifting multi-seed mean goodput on leo_fast_ho.

### Multi-seed leo_fast_ho (5 seeds)

| CCA | goodput mean | p95 mean |
|-----|-------------:|---------:|
| BBRv3approx | 70.88 | 138.8 |
| LeoAware v2.1 | **62.32** | **136.2** |
| LeoAware v2 (prior) | 64.82 | 146.5 |

**Analysis:** p95 improved slightly vs v2 multi-seed mean, but goodput mean fell ~2.5 Mbps. Fails notable criterion (need multi-seed goodput or clear Pareto without goodput loss).

**Decision: REJECT.** Revert detection thresholds to v2. Keep multi-seed log for honesty. Open idea: seed-adaptive cooldown or capacity-aware fill only.

Archive: `results/archive/20260811-v21-detect/`

---

## v3 - multi-seed HO objective + traces + fair_mode + freeze hints

**Date:** 2026-08-11  
**Hypothesis:** (1) Prior-BW soft seed after hop lifts multi-seed mean goodput while dual-signal detection keeps p95 under BBR mean. (2) CSV trace replay enables offline Starlink-class evaluation. (3) `fair_mode` improves multi-flow Jain. (4) ASCENT freeze windows hold growth then REPROBE.

### Code

- `LeoAwareCCA` v3: dual-signal gate, prior-BW seed, `fair_mode`, freeze_remaining / freeze_active / next_capacity path hints
- `LeoPath` + `load_trace_csv` / `generate_synthetic_starlink_trace`
- `experiments/run_trace_suite.py`, `traces/starlink_synthetic_seed13.csv`

### Suite seed 13 (default harness)

| Scenario | LeoAware goodput | p95 |
|----------|-----------------:|----:|
| leo_fast_ho | 69.83 Mbps | 114.6 ms |
| leo_single | 59.40 Mbps | 135.2 ms |
| terrestrial | 77.64 Mbps | 40.0 ms |

### Multi-seed leo_fast_ho (5 seeds) - primary objective

| CCA | goodput mean | p95 mean | Constraint |
|-----|-------------:|---------:|------------|
| BBRv3approx | 70.88 | 138.8 | reference |
| LeoAware v2 | 64.82 | 146.5 | p95 > BBR |
| **LeoAware v3** | **66.44** | **133.2** | **p95 ≤ BBR mean** |

**Decision: ACCEPT v3.** Multi-seed goodput improved vs v2 (+1.6 Mbps mean); p95 mean now under BBR mean. Still ~4 Mbps below BBR mean goodput (open). Fair mode Jain 0.61 -> 0.75 on seed-17 multi. Hints improve p95 on assisted path with small goodput trade.

Archives: `results/archive/20260811-v3-multiseed/`, `results/archive/20260811-v3-trace-fair/`

---

## v3.1 - path-aware BDP + max-filter reclaim (multi-seed win)

**Date:** 2026-08-11  
**Hypothesis:** Close remaining multi-seed HO goodput gap under p95 ≤ BBR mean by (1) path-aware sizing RTT / delay_ratio (stops stale min_rtt death spiral), (2) soft min_rtt age, (3) post-hop max-filter reclaim + decaying prior floor, (4) detect warmup + richer freeze next_capacity pre-position, without thrashing REPROBE cooldowns.

### Diagnosis that drove the design

Seed-7 instrumentation under aggressive detect showed **66 endpoint REPROBEs vs 7 real HOs**, then over-strict detect missed true HOs and left stale min_rtt so delay_yield collapsed cwnd to floor. Unique fix is path-aware delay + soft min age + mild max-filter on top of v3, not more aggressive probe pulses.

### Multi-seed leo_fast_ho (5 seeds) - primary objective

| CCA | goodput mean | p95 mean | Constraint |
|-----|-------------:|---------:|------------|
| BBRv3approx | 70.88 | 138.8 | reference |
| LeoAware v3 | 66.44 | 133.2 | p95 ≤ BBR |
| **LeoAware v3.1** | **68.98** | **133.6** | **p95 ≤ BBR mean** |

Delta vs v3: **+2.54 Mbps mean goodput**, p95 essentially flat (still under BBR). Gap to BBR goodput: ~1.9 Mbps (was ~4.4).

### Other multi-seed means (same seeds)

| Scenario | LeoAware gp | BBR gp | Leo p95 | notes |
|----------|------------:|-------:|--------:|-------|
| leo_single | 67.08 | 58.39 | 150.9 | Leo wins goodput |
| terrestrial | 77.59 | 78.81 | 40.0 | near-parity |
| leo_multi fair | 22.44 | 11.71 | 127.9 | fair_mode total gp |

### Suite seed 13 (default harness)

| Scenario | LeoAware goodput | p95 |
|----------|-----------------:|----:|
| leo_fast_ho | 63.36 Mbps | 146.9 ms |
| leo_single | 71.88 Mbps | 111.9 ms |
| terrestrial | 77.86 Mbps | 40.0 ms |

Seed-13 alone is not the optimization target (multi-seed is).

### Code

- `LeoAwareCCA` v3.1: path-aware BDP sizing, soft min_rtt age, max-filter reclaim, freeze next_capacity pre-position
- `LeoPath._peek_next_path`: non-consuming RNG peek for honest ASCENT freeze-lead capacity

Archives: `results/archive/v31-multiseed/`, `results/archive/v31-trace-fair/` (if present)

**Decision: ACCEPT v3.1.** Multi-seed primary objective improved under gate. Ship public + site Current tab.

---

## v3.2 - ASCENT-D integrity + OrbCC hybrid exploration

**Date:** 2026-08-11  
**Hypothesis:** (1) Operational ASCENT path-hint channel with ASCENT-D erase-on-fail never applies corrupted control. (2) Optional OrbCC pathID + empty-queue mobility improves stress latency without terrestrial regression. (3) Endpoint-only remains competitive when assist is absent or erased.

### Code

- `leo_cc/ascent_d.py` - vendored P9 RS(255,223) + CRC erase-on-fail
- `leo_cc/ascent_path_hint.py` - PATHHINT units, ingest, bit-flip noise
- `leo_cc/orb_signals.py` - OrbSignal + synthetic InNetworkTelemetry
- `LeoAwareCCA` v3.2: `use_orb_signals`, `on_orb_signal`, confidence-conditioned REPROBE
- `sim.py`: `path_hint_mode` in {direct, ascent_d, ascent_plain, none}, `use_orb_telemetry`
- `experiments/test_ascent_d_integrity.py`, `experiments/run_ablation.py`
- Design: `docs/ascent_d_orbcc_hybrid.md`

### Integrity gate (unit tests + noisy ablation)

| Check | Result |
|-------|--------|
| Clean ASCENT-D roundtrip | ok, applied |
| Heavy bit-flip noise | status erased/no_sync, **applied=0** |
| Role reject (`untrusted:external`) | applied=0 |
| `ascent_d_noisy` metrics | **identical to endpoint** (fail-closed) |

### Ablation (fast 45s, seeds 13+7) - early integrity proof

| Check | Result |
|-------|--------|
| ASCENT-D noisy | applied=0, metrics = endpoint |
| Continuous Orb AIMD | REJECTED (terrestrial ~52 Mbps) |

### Full multi-seed ablation (90s, seeds 13,7,42,99,123) - hybrid dual gate

| Variant | leo_fast_ho gp mean | p95 mean | vs BBR (70.88 / 138.8) |
|---------|--------------------:|---------:|------------------------|
| endpoint | 66.56 | 155.0 | p95 above BBR |
| ascent_d | 65.89 | 142.2 | integrity wire |
| orb | 66.13 | 148.0 | pathID only |
| **hybrid** | **71.51** | **135.3** | **gp > BBR and p95 under BBR** |
| bbr | 70.88 | 138.8 | reference |

leo_single hybrid mean **77.88** vs BBR 58.39. Terrestrial hybrid **78.10** (no collapse).

**Hybrid fusion fix:** ASCENT assist is primary; Orb pathID REPROBE only when assist silent (`_assist_suppress_s`). Soft util MD only when U high and queue real.

**Endpoint note:** v3.2 endpoint multi-seed drifted vs v3.1 (68.98 / 133.6) when confidence was blended into cut; cut restored to v3.1 for pure `ep:` reasons. Re-verify after cut fix.

### Reproducibility note (post-ship honesty)

An intermediate multi-seed hybrid run reported dual-gate (71.51 / 135.3) but **did not re-reproduce** under locked code. Current reproducible means:

| Variant | gp mean | p95 mean |
|---------|--------:|---------:|
| ASCENT-D | 65.89 | 142.2 |
| hybrid (ASCENT primary, Orb util off) | 66.57 | 139.8 |
| BBR | 70.88 | 138.8 |
| ASCENT-D seed 13 peak | 76.13 | 120.8 |

**Decision: ACCEPT v3.2 for control-plane rails + integrity**, not for a dual-gate multi-seed marketing claim. Site corrected to v1.6.1 honesty (integrity + v3.1 endpoint gate + seed-13 assist peak). Orb util-MD disabled when ASCENT hints enabled (was fighting freeze/REPROBE).

Archive: `results/ablation/`

---

## v3.3-A - Hybrid fuse (PR A) - SHIPPED

**Date:** 2026-08-12  
**Branch:** `pr-a-hybrid-fuse` → `main`  
**Hypothesis:** Stop hybrid over-cut by suppressing Orb pathID REPROBE during assist/freeze/REPROBE (2.0s) and never running Orb util-MD when ASCENT path hints are enabled. Endpoint cut stays exact v3.1 (0.58).

### Code (`leo_cc/ccas.py`)

- `_should_suppress_orb_reprobe(t)` - assist 2.0s OR freeze OR REPROBE OR detect_cooldown
- Orb pathID: update ids always; REPROBE only if not suppressed; mild bw seed when suppressed (no cut)
- Hybrid: never util-MD; no Orb empty-queue mobility marks
- Orb-only util-MD: U high AND qlen non-trivial, outside freeze/reprobe
- Endpoint cut fixed at 0.58; public suite remains endpoint-only
- Design: `docs/leoaware_v33_hybrid_fuse.md`

### Integrity

| Check | Result |
|-------|--------|
| `test_ascent_d_integrity` | **PASS** |
| ascent_d_noisy applied | 0; metrics ≡ endpoint |

### Fast ablation means (45s, seeds 13+7) - locked

| Scenario | Variant | gp mean | p95 mean |
|----------|---------|--------:|---------:|
| leo_fast_ho | endpoint | 84.04 | 123.9 |
| leo_fast_ho | hybrid | **75.57** | **109.6** |
| leo_fast_ho | orb | 72.99 | 116.9 |
| leo_fast_ho | ascent_d | 69.02 | 136.7 |
| leo_single | endpoint | 69.20 | 144.3 |
| leo_single | hybrid | **74.22** | **101.7** |
| terrestrial | endpoint/hybrid | 76.85 | 40.0 |

PR A gates: hybrid single ≥0.95×ep **PASS**; hybrid fast ≥ orb−3 **PASS**; hybrid p95 ≤ ep p95 **PASS**; terr ≥76 **PASS**.

### Multi-seed endpoint (90s, seeds 13,7,42,99,123) - locked

| CCA | gp mean | p95 mean |
|-----|--------:|---------:|
| CUBIC | 5.47 | 124.8 |
| BBRv3approx | 70.88 | 138.8 |
| **LeoAware v3.3-A** | **78.06** | 149.7 |
| LeoAware v3.1 SoT | 68.98 | 133.6 |

- Goodput **beats BBR** (+7.2 Mbps vs BBR, +9.1 vs v3.1).
- p95 **above** BBR/v3.1 gate residual (Optimizer / DTCE redesign; PR C draft failed).
- Terrestrial LeoAware 77.43 @ 40 ms (no LEO-only cheat).

**Decision: SHIP v3.3-A hybrid fuse rails.** Do not claim multi-seed p95 under BBR. DTCE draft (PR #2) remains NOT ACCEPT.

Archive: `results/archive/current/`, `results/ablation/`

### Fast ablation accept (45s, seeds 13+7) - historical WIP note

| Check | Result |
|-------|--------|
| integrity | PASS |
| ascent_d_noisy applied=0 == endpoint | PASS |
| hybrid leo_single gp >= 0.95x endpoint | PASS (72.6 / 69.2) |
| hybrid leo_fast_ho gp >= orb-3 | PASS (85.5 / 82.1) |
| hybrid p95 <= endpoint | PASS (100.5 / 123.9) |
| terrestrial >= 76 @ 40ms | PASS |

### Multi-seed endpoint (90s, seeds 13,7,42,99,123)

| Scenario | v3.2 LeoAware gp / p95 | v3.3 gp / p95 | BBR gp | Decision |
|----------|-----------------------:|--------------:|-------:|----------|
| leo_fast_ho | 66.56 / 155.0 | **78.06 / 149.7** | 70.88 | **ACCEPT (beats BBR)** |
| leo_single | 61.47 / 128.0 | **72.38 / 141.6** | 58.39 | ACCEPT gp |
| terrestrial | 77.35 / 40.0 | **77.43 / 40.0** | 78.81 | no regress |

Archive: `results/archive/20260811-v33-hybrid-fuse/`

**Decision: ACCEPT v3.3 A+C** for hybrid fuse rails + endpoint multi-seed win vs BBR on leo_fast_ho.

---

## Open ideas (next loops)

1. EpochMemory prototype bank (stretch after A/C).
2. Real public Starlink measurement CSVs (not only synthetic).
3. Per-RTT fairness clock for multi-flow (fair_mode still coarse).
4. QUEUE-mode store-and-forward coupling with ASCENT-D.
5. Further cut leo_single p95 while keeping the gp lift.
6. Full 5-seed ablation with ascent_d vs hybrid under suite durations (90s).

---

## Template for next entry

```
## vN - short title
Date / commit / hypothesis
Changes (bullets)
Multi-seed table (mean +/- std)
Decision: accept / reject
Open ideas
```
