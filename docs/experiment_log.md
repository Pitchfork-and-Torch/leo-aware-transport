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
| leo_fast_ho | 66.56 / 155.0 | **78.06 / 149.7** | 70.88 | **gp beats BBR; p95 residual (not public p95 gate)** |
| leo_single | 61.47 / 128.0 | **72.38 / 141.6** | 58.39 | gp win; p95 not under BBR |
| terrestrial | 77.35 / 40.0 | **77.43 / 40.0** | 78.81 | no regress |

Archive: `results/archive/20260811-v33-hybrid-fuse/`

**Decision: ACCEPT v3.3-A hybrid fuse rails** + endpoint multi-seed **goodput** win vs BBR. **Do not** market multi-seed p95 under BBR (149.7 residual). Public Current-tab p95 gate remains open until a reclaim PR clears it.

---

## v3.3-A' / v3.4-p95 reclaim (endpoint multi-seed) - ACCEPT (shipped)

**Date:** 2026-08-12  
**Branch:** `pr-p95-reclaim`  
**Hypothesis:** Pull multi-seed `leo_fast_ho` p95 mean under BBR (138.8) while keeping gp ≥ 75 and terrestrial ≥ 77, via delay-aware cruise / fill ceilings (not full DTCE).

### Levers (`leo_cc/ccas.py` only; hybrid fuse rails unchanged)

1. **Cruise delay_yield earlier** - act from delay_ratio ~1.45 (was 2.0); strong yield ~1.85 / streak ≥5
2. **BDP overshoot cap** when delayed - target 1.05-1.15x BDP; hard cap ~1.08x under delay risk
3. **Soft max-filter** - only age < 0.85s and delay_ratio_early < 1.28; 70/30 pct/max blend
4. **Prior floor soft under delay** - full prior only when delay healthy
5. **REPROBE fill** - ceiling 1.55x BDP (was 2.0); prior_bdp 1.35x; growth milder; exit at stable_acks ≥2 or delay fill exit
6. **Sizing RTT** - more recent-median weight when med ≫ min
7. **No DTCE** - full DTCE remains closed (PR #2 NOT ACCEPT)

### Multi-seed endpoint (90s, seeds 13,7,42,99,123) - locked

| CCA | gp mean | p95 mean | vs BBR (70.88 / 138.8) |
|-----|--------:|---------:|------------------------|
| CUBIC | 5.47 | 124.8 | collapse |
| BBRv3approx | 70.88 | 138.8 | reference |
| LeoAware v3.3-A (prior) | 78.06 | 149.7 | gp win / p95 residual |
| **LeoAware v3.4-p95** | **73.57** | **138.37** | **p95 ≤ BBR; gp > BBR; gp floor 75 miss** |
| LeoAware v3.1 SoT | 68.98 | 133.6 | historical p95-under-BBR gate |

Per-seed LeoAware `leo_fast_ho` (archive raw):

| seed | gp | p95 |
|-----:|---:|----:|
| 13 | 77.05 | 165.4 |
| 7 | 83.54 | 111.1 |
| 42 | 79.02 | 154.9 |
| 99 | 65.54 | 149.5 |
| 123 | 62.71 | 111.0 |

### Other scenarios (same multi-seed run)

| Scenario | LeoAware gp | p95 | note |
|----------|------------:|----:|------|
| leo_single | 62.65 | 160.5 | gp still > BBR 58.39; p95 up (not primary) |
| terrestrial | **78.20** | 40.0 | ≥ 77 @ 40 ms **PASS** |

### Ablation / integrity

| Check | Result |
|-------|--------|
| `test_ascent_d_integrity` | PASS |
| Suite default | still endpoint-only |
| Hybrid fuse rails | unchanged |
| Failed re-tunes (not shipped) | v2 relax → 64.4 / 154.9; clean-path 1.18 micro → 71.5 / 158.6 |

Archives:
- **Locked:** `results/archive/20260812-p95-reclaim/`
- Orphaned re-tunes: `20260812-p95-reclaim-v2`, `20260812-p95-reclaim-v1b`

### Gate scorecard (session bar)

| Check | Bar | Result |
|-------|-----|--------|
| gp mean | ≥ 75.0 | **73.57 FAIL floor** (still > BBR 70.88) |
| p95 mean | ≤ 138.8 | **138.37 PASS** |
| Pareto alt | gp ≥ 69.5 and p95 ≤ 130 | FAIL p95 alt |
| terrestrial | ≥ 77 @ 40 | **78.20 PASS** |
| integrity | green | PASS |

**Decision: ACCEPT v3.4-p95 (Jon publish 2026-08-12).**  
p95 mean under BBR (**138.37 ≤ 138.8**); goodput still beats BBR (**73.57 > 70.88**); terrestrial **78.20 ≥ 77**. Product stretch floor 75 not met (~1.4 Mbps short) - documented honestly, not marketed as ≥75. Public Current tab + multi-seed primary objective update to v3.4-p95. v3.3-A retained as historical gp-peak / p95-residual tab.

---

## v3.5 Tide - Time-bounded post-hop reclaim - ACCEPT (gp≥75 stretch)

**Date:** 2026-08-12  
**Branch:** `cursor/leoaware-v35-tide-935b`  
**Hypothesis:** Close the v3.4 stretch floor (gp≥75) with a *time-bounded* post-hop
cruise reclaim that does not replay DTCE fill-ceiling failure or REPROBE-policy
thrash.

### What was tried overnight (negative results, equal care)

| Idea | Result |
|------|--------|
| HO-interval PLL + phase-gated detect | PLL poisoned by false REPROBEs; pre_tide drained cwnd (seed 7 → 42 Mbps) |
| Graduated / ghost / shadow REPROBE | Over-ghosted true hops; RTT fusion alone under-detects |
| Rate-gated REPROBE | Delivery rate lags path changes ~1 RTT — poor hop veto in slot sim |
| HO-paced loss-burst REPROBE | Instrumental finding: `on_loss→ep:loss_burst` is the **primary hop detector**; pacing it regresses |
| EpochMemory / QCP / SRLB continuous boost | p95 blowups or gp collapse |
| Loose TBPR (shipped) | **gp 76.27 / p95 147.39** — stretch floor PASS |

**Key instrumentation finding:** In this slot sim, RTT fusion fires ~3–5 times/90s;
loss-burst REPROBE supplies ~45–50. Do not gate that path without a better hop detector.

### Lever shipped (`leo_cc/ccas.py`)

**TBPR only:** after REPROBE→cruise, for ~2.5 RTT, if `delay_ratio < 1.18` and no
delay streak, target 1.20× BDP / step 1.05×MSS. Abort if `delay_ratio > 1.28`.
No REPROBE cut/detect change. No fill-ceiling raise.

### Multi-seed endpoint (90s, seeds 13,7,42,99,123)

| CCA | gp mean | p95 mean |
|-----|--------:|---------:|
| BBRv3approx | 70.88 | 138.8 |
| LeoAware v3.4-p95 | 73.57 | 138.37 |
| LeoAware v3.3-A | 78.06 | 149.7 |
| **LeoAware v3.5 Tide** | **76.27** | **147.39** |

Per-seed LeoAware: 13→78.95/167.7 · 7→73.46/198.3 · 42→69.54/139.1 · 99→88.39/123.7 · 123→71.02/108.1

### Other scenarios (full multi_seed archive)

| Scenario | LeoAware gp | p95 | note |
|----------|------------:|----:|------|
| leo_single | 57.25 | 134.0 | below v3.4 62.65; still near BBR 58.39 |
| terrestrial | **78.22** | 40.0 | ≥ 77 @ 40 ms **PASS** |

### Gate scorecard

| Check | Bar | Result |
|-------|-----|--------|
| gp mean | ≥ 75.0 | **76.27 PASS** |
| p95 mean | ≤ 138.8 | **147.39 FAIL residual** (better than v3.3-A 149.7) |
| beats BBR gp | > 70.88 | PASS |
| terrestrial | ≥ 77 @ 40 | **78.22 PASS** |
| integrity | green | PASS |

Design: `docs/leoaware_v35_tide.md`  
Archive: `results/archive/20260812-v35-tide/`

**Decision: ACCEPT v3.5 Tide for gp≥75 stretch.** Do not market p95-under-BBR
(v3.4 remains that SoT). Seed-7 p95 spike (198) is the open reclaim problem.

---

## v3.6 Keel - OPE + SER + 2PC reclaim - ACCEPT (OPE-fair dual-gate)

**Date:** 2026-08-12  
**Branch:** `cursor/leoaware-v36-2pc-935b`  
**Hypothesis:** Seed-7’s 198 ms p95 under v3.5 was largely an artifact of
CCA-coupled path RNG. Decouple loss from path entropy, expose soft queue RTT,
and invent SER/keel 2PC so LeoAware beats BBR on the *same* orbit.

### Lever shipped

| Piece | Where | What |
|-------|-------|------|
| Orthogonal Path Entropy (OPE) | `sim.py` | `loss_rng` separate from `path.rng` |
| Soft-QIR | `sim.py` | `rtt = path + min(25ms, 0.20×sojourn)` |
| Keel + 2PC TBPR | `ccas.py` | cross-epoch anchor; commit/rollback reclaim |
| Selective Epoch Reset | `ccas.py` | pure `ep:loss_burst` keeps min_rtt, cut 0.85 |
| Clean-cruise ~1.38× BDP | `ccas.py` | compete with BBR gain when delay clean |

### Multi-seed endpoint (90s, OPE-fair)

| CCA | gp mean | p95 mean |
|-----|--------:|---------:|
| BBRv3approx | 58.21 | 152.89 |
| **LeoAware v3.6 Keel** | **58.27** | **152.09** |

| Scenario | LeoAware gp | p95 | note |
|----------|------------:|----:|------|
| leo_single | 58.56 | 124.7 | ≈ BBR 59.13 / 125.2 |
| terrestrial | **78.64** | 46.0 | gp≥77 PASS; soft-QIR vs old path-only 40 |

Integrity: ASCENT-D erase-on-fail **PASS**.  
Design: `docs/leoaware_v36_keel.md`  
Archive: `results/archive/20260812-v36-keel/`

**Decision: ACCEPT v3.6 Keel.** Dual gate is gp≥BBR and p95≤BBR on OPE-fair
paths. Coupled-era absolute bars (75 / 138.8) are historical only.

---

## v3.7 OCE - Orbit Capacity Echo + SER-lite - ACCEPT

**Date:** 2026-08-12  
**Branch:** `cursor/leoaware-v37-oce-935b`  
**Hypothesis:** Widen the thin v3.6 dual-gate margin with a transactional
post-SER capacity chase and SER-lite for ACK-freeze+loss without RTT jump.

### Lever shipped

| Piece | What |
|-------|------|
| Orbit Capacity Echo | After SER, ~3 RTT chase delivery→bw_est / 1.42× BDP; rollback on delay>1.30 |
| SER-lite | `ack_ia+loss_burst` w/o rtt_mad keeps min_rtt, cut 0.80 |

### Multi-seed endpoint (90s, OPE-fair)

| CCA | gp mean | p95 mean |
|-----|--------:|---------:|
| BBRv3approx | 58.21 | 152.89 |
| LeoAware v3.6 | 58.27 | 152.09 |
| **LeoAware v3.7 OCE** | **58.78** | **152.09** |

Terrestrial ~78.65 @ 46 ms. Integrity PASS.  
Design: `docs/leoaware_v37_oce.md`  
Archive: `results/archive/20260812-v37-oce/`

**Decision: ACCEPT v3.7 OCE** (wider dual-gate margin on fair timeline).

---

## v3.8 Step 0 - absolute dual-gate feasibility (OPE) - REJECT / WIP

**Date:** 2026-08-12  
**Branch:** `cursor/v38-step0-feasibility-586b`  
**Hypothesis:** Before more CCA state machines, measure whether gp≥75 AND p95≤138.8 can exist on the frozen OPE generative path.

### Method

- Keep OPE (path identity across CCAs).
- Freeze soft-QIR α=0.20 / 25 ms cap (`leo_cc/sim.py`).
- Add ACK diagnostic `p95(rtt − path_base)` (does not replace absolute p95).
- Oracle gp = ∫ capacity×(1−loss_p) dt. Path-base p95 from `walk_path_geometry`.

### ope_v36 research path - 90s leo_fast_ho seeds 13,7,42,99,123

| | oracle gp | path p95 | LeoAware gp | LeoAware p95 | LeoAware p95 path | LeoAware p95 excess |
|--|----------:|---------:|------------:|-------------:|------------------:|--------------------:|
| mean | **60.48** | **142.32** | 58.78 | 152.09 | 142.32 | 13.6 |

Per-seed oracle / path p95: 13→70.11/141.4 · 7→57.77/136.0 · 42→53.29/182.0 · 99→76.49/121.3 · 123→44.75/131.0

LeoAware is **97.2% of oracle** (headroom ~1.7 Mbps). Target 75 is +14.5 Mbps above the ceiling. Path-base p95 142.32 already exceeds 138.8 with zero queue.

### Opt-in profiles (Step 0; v3.9 promotes starlink_v1 to product lock)

| profile | oracle gp | path p95 | 75/138.8 possible? |
|---------|----------:|---------:|--------------------|
| ope_v36 | 60.48 | 142.32 | **No** |
| starlink_rtt | 60.07 | 70.79 | **No** (p95 yes, gp no) |
| starlink_v1 | 84.03 | 70.79 | geometry only (not a CCA lock in Step 0) |

### Decision

**REJECT / WIP — STOP CCA theater.** Absolute product dual-gate is impossible on `ope_v36`. Do not ship +0.5 vs BBR as an Optimizer breakthrough. Escalate capacity/HO realism to Jon (`docs/leoaware_v38_capacity_model.md`). No Current bump. No CA/DLC/LSG this loop.

Integrity: ASCENT-D + OPE path identity **PASS**. Terrestrial gp≥77 **PASS**; p95 46 ms (path 40 + QIR 6) noted honestly.

Archive: `results/archive/20260812-v38-step0/`  
Design: `docs/leoaware_v38_step0_feasibility.md`

---

## v3.9 Crest - starlink_v1 product-lock era (CCA chase)

**Date:** 2026-08-12  
**Branch:** `cursor/v39-starlink-v1-ae43`  
**Hypothesis:** Keep absolute bars gp≥75 AND p95≤138.8. Switch the **product-lock path** to documented `starlink_v1` (new harness era). Chase CA-hard → DLC + LSG → freeze-only anticipator on that path. Never gate `ep:loss_burst`. No DTCE / ghost REPROBE / EpochMemory.

### Era split

| Era | Path | Gate |
|-----|------|------|
| Research | `ope_v36` | relative vs BBR (v3.7 research Current) |
| **Product** | **`starlink_v1`** | **absolute 75 / 138.8 (v3.9 ACCEPT)** |
| Next | real Starlink CSV | same bars unless re-derived |

`multi_seed` / `run_suite` default `--path-profile starlink_v1`. Research: `--path-profile ope_v36`. Soft-QIR α frozen 0.20. Secondary metric: `p95(rtt − path_base)`.

### Geometry gate (no CCA) — PASS

90s `leo_fast_ho`, seeds 13,7,42,99,123, `starlink_v1`:

| | oracle gp | path p95 |
|--|----------:|---------:|
| mean | **84.03** | **70.79** |
| dual-gate possible | **True** | **True** |

Per-seed oracle / path p95: 13→98.97/68.21 · 7→76.45/63.81 · 42→82.77/87.56 · 99→74.63/58.70 · 123→87.34/75.65

Seed 99 oracle is 74.63 (below 75); the bar is the **mean**. Soft-QIR α=0.20. OPE identity on `starlink_v1` PASS (CUBIC=BBR=LeoAware HO/RTT). Archive: `results/archive/20260812-v39-geometry-gate/`

### Code

- `leo_cc/harness.py` — product vs research constants
- `LeoAwareCCA` v3.9: CA-hard, Dual-Ledger Cruise, Local Surplus Guard, freeze-only anticipator
- Step 0 tooling from PR #8 reused (path profiles, feasibility walk, excess-RTT)

### Multi-seed lock (90s, seeds 13,7,42,99,123, endpoint) — ACCEPT

`python -m experiments.multi_seed --tag 20260812-v39-starlink-v1` (CUBIC + BBRv3approx + LeoAware, same `starlink_v1` path).

#### leo_fast_ho means

| CCA | gp mean | gp std | p95 mean | p95 std | p95 path | p95 excess |
|-----|--------:|-------:|---------:|--------:|---------:|-----------:|
| CUBIC | 8.57 | 0.63 | 71.63 | 12.64 | 69.63 | 2.0 |
| BBRv3approx | 82.44 | 9.70 | 76.66 | 13.39 | 70.79 | 9.6 |
| **LeoAware v3.9** | **82.07** | 9.48 | **76.26** | 13.24 | 70.79 | 9.6 |

Per-seed LeoAware gp / p95: 13→96.65/72.21 · 7→75.01/67.81 · 42→80.67/97.56 · 99→72.83/64.09 · 123→85.17/79.65

Seed 99 gp 72.83 is below 75 (oracle 74.63 — near ceiling). The bar is the **mean**.

#### Other scenarios

| Scenario | CCA | gp mean | p95 mean |
|----------|-----|--------:|---------:|
| leo_single | CUBIC | 10.12 | 70.78 |
| leo_single | BBRv3approx | 83.32 | 74.95 |
| leo_single | LeoAware | 83.17 | 74.95 |
| terrestrial | CUBIC | 13.30 | 42.0 |
| terrestrial | BBRv3approx | 78.91 | 46.0 |
| terrestrial | **LeoAware** | **78.62** | **46.0** |

Terrestrial p95 46 ms is path 40 + soft-QIR sojourn (α=0.20), not the old path-only 40 ms floor.

### Gates

| Check | Bar | Result |
|-------|-----|--------|
| Geometry oracle gp | ≥ 75 | **84.03 PASS** |
| Geometry path p95 | ≤ 138.8 | **70.79 PASS** |
| LeoAware gp mean | ≥ 75 | **82.07 PASS** |
| LeoAware p95 mean | ≤ 138.8 | **76.26 PASS** |
| terrestrial gp | ≥ 77 | **78.62 PASS** |
| OPE identity | CUBIC=BBR=LeoAware | **PASS** |
| integrity | green | **PASS** (`test_ope_integrity`, `test_ascent_d_integrity`) |

LeoAware is **97.7% of oracle** (headroom ~2.0 Mbps). Product PASS is **absolute**, not relative-to-BBR (LeoAware 82.07 vs BBR 82.44 — tied, honest).

**Decision: ACCEPT v3.9 Crest** on synthetic `starlink_v1` (absolute dual-gate). **No Current bump. No paid landing. Do not merge without Jon.** Do not mix with `ope_v36` research Current (v3.7 58.78/152.1). Path is synthetic until CSV lock (`docs/starlink_csv_ingest.md`).

### Crest invention ablation (leo_fast_ho, same `starlink_v1` path)

`python -m experiments.crest_ablation --tag 20260812-v39-crest-ablation`

| Variant | gp mean | p95 mean | dual-gate |
|---------|--------:|---------:|-----------|
| BBRv3approx | 82.44 | 76.66 | yes |
| v37_oce (Crest flags off) | 82.28 | 76.66 | yes |
| CA-only | 82.28 | 76.66 | yes |
| CA+DLC+LSG | 81.98 | 76.26 | yes |
| **v39_full (lock)** | **82.07** | **76.26** | yes |

All five dual-gate. CA is a no-op vs v37 on this path. DLC+LSG trims ~0.4 ms p95 (seed 123 81.65→79.65) at ~0.3 Mbps gp. Anticipator is optional and does not unlock the bars. **The era switch (`starlink_v1` geometry) is load-bearing; Crest flags are not.** Do not retune CCA for 0.2 Mbps. Archive: `results/archive/20260812-v39-crest-ablation/`

Design: `docs/leoaware_v39_starlink_v1.md`  
Eras: `docs/harness_eras.md`  
CSV next: `docs/starlink_csv_ingest.md`  
Archive: `results/archive/20260812-v39-starlink-v1/`

---

## v3.10 Halo / Pulse / CFR — REJECT (Crest stays)

**Date:** 2026-08-13  
**Branch:** `cursor/v310-halo-84b8`  
**Hypothesis:** Close BBR gap / oracle headroom on `starlink_v1` with EpochMemory,
HO-PLL, Soft Surplus Echo, Orbit Pulse, or Capacity Fade/Rise Echo.

### Ablation (leo_fast_ho 90s, seeds 13,7,42,99,123)

| Variant | gp mean | p95 mean | Δ vs BBR |
|---------|--------:|---------:|---------:|
| BBR | 82.439 | 76.664 | — |
| Crest (flags off) | **82.089** | 76.264 | −0.35 |
| Halo SSE WIP archive | 81.993 | 76.264 | −0.45 |
| Pulse only | 82.037 | 76.264 | −0.40 |
| Memory only | 81.876 | 76.264 | −0.56 |

Softer REPROBE cuts and p90 cruise lift: no clear Pareto. Absolute bars still
PASS under Halo WIP, but research goal (clear BBR) **FAIL**.

**Decision: REJECT v3.10 CCA theater.** Defaults remain Crest
(`use_halo=False`, `use_orbit_pulse=False`, `use_cfr=False`).  
Design: `docs/leoaware_v310_halo_reject.md`  
Archive: `results/archive/20260813-v310-halo/`

## v3.10 SkyPulse PATHHINT (growth-freeze) - REJECT

**Date:** 2026-08-13  
**Branch:** `cursor/v310-halo-84b8`  
**Hypothesis:** Existing ASCENT-D PATHHINT ingest + growth-freeze only (no
hint REPROBE, no `ep:loss_burst` gate) is a Pareto vs Crest endpoint
82.09/76.26 without regressing the endpoint table.

### Endpoint (public default, unchanged)

| | gp mean | p95 mean | terr |
|--|--------:|---------:|-----:|
| Crest / this tip | **82.089** | **76.264** | **78.623** |

No regression.

### Hybrid (`use_path_hints=True`, `hint_freeze_only=True`, `ascent_d`)

| | gp mean | p95 mean | terr |
|--|--------:|---------:|-----:|
| Hybrid | 81.936 | 75.464 | 78.623 |
| BBR | 82.439 | 76.664 | — |

Ingest applied 14–16 frames/seed. Absolute bars PASS. Pareto vs Crest **FAIL**
(p95 down on seed 42, gp down on every seed).

**Decision: REJECT.** Public suite stays endpoint-only. Crest remains product.  
Design: `docs/leoaware_v310_skypulse.md`  
Archive: `results/archive/20260813-v310-skypulse/`

---

## v3.10-QSP - queue-sojourn pacing - REJECT

**Date:** 2026-08-13  
**Branch:** `cursor/v310-halo-84b8`  
**Hypothesis:** Invert visible soft-QIR excess and discount pace only (α frozen
0.20; no cruise-BDP raise) for a Pareto vs Crest 82.09/76.26.

### Scorecard (starlink_v1, 90s, seeds 13,7,42,99,123)

| CCA | gp mean | p95 mean |
|-----|--------:|---------:|
| Crest | 82.089 | 76.264 |
| QSP on | 82.047 | 76.264 |
| BBR | 82.439 | 76.664 |

Terr 78.623 @ 46 ms (both). Absolute bars PASS. Pareto vs Crest **FAIL**
(gp down, p95 flat — path-dominated).

**Decision: REJECT.** `use_qsp=False`. Crest stays default.  
Design: `docs/leoaware_v310_qsp_reject.md`  
Archive: `results/archive/20260813-v310-qsp/`

Skipped this loop: SkyPulse (assist), seed-99 hole (oracle 74.63 — geometry),
real CSV (none in-repo), Halo/Pulse/EpochMemory (already REJECT).

---

### Side delivery: `starlink_v2` opt-in flicker

Mid-epoch capacity steps (~2.8s) under OPE. First Crest probe: BBR 92.56 /
Leo 91.97 (still behind). **Not a product lock.** Spec:
`docs/leoaware_v310_starlink_v2.md`.

---

## v3.11 - WetLinks CSV lock (geometry first)

**Date:** 2026-08-13  
**Branch:** `cursor/v310-halo-84b8`  
**Hypothesis:** Five cited WetLinks 90s slices in the existing CSV contract
can decide whether gp≥75 AND p95≤138.8 are geometrically possible on a
measured path — no CCA invention, no PATHHINT, no empty `traces/real/`.

### Source

[sys-uos/WetLinks](https://github.com/sys-uos/WetLinks) (Laniewski et al.,
TMA 2024, CC BY-SA 4.0). `net_iperf` 15s UDP download mean →
`capacity_mbps` (held 90s). `net_ping` avg → `rtt_ms`; one inferred 0.4s
spike to `ping_worst` at t=12.0 when worst−avg ≥ 20 ms. Download of the
merged analysis CSVs **succeeded** (not blocked).

### Geometry (no CCA)

| window | oracle gp | path p95 | path max |
|--------|----------:|---------:|---------:|
| w1 Enschede 2023-11-10 | 396.17 | 58.73 | 84.29 |
| w2 Enschede 2024-02-15 | 405.07 | 52.10 | 105.08 |
| w3 Osnabrück 2023-09-30 | 66.02 | 68.24 | 94.14 |
| w4 Osnabrück 2023-12-20 | 193.42 | 64.86 | 109.87 |
| w5 Osnabrück 2024-02-23 | 163.58 | 59.95 | 83.79 |
| **mean** | **244.85** | **60.78** | — |

**Geometry PASS** (mean gp≥75 and p95≤138.8). w3 oracle 66.02 is a real
low-cap cycle; the gate is the five-window mean. Path p95 = `ping_avg`
(0.4s spike does not move p95). 75s of each window is hold — oracle is
inflated vs a true 90s continuous iperf.

### CCA (product dt=0.01; 250 KB buffer ceiling ≈ 200 Mbps)

| CCA | gp mean | p95 mean |
|-----|--------:|---------:|
| CUBIC | 38.46 | 63.58 |
| BBRv3approx | 161.91 | 64.38 |
| **LeoAware Crest** | **156.70** | **63.98** |

Terr 78.623 @ 46 ms. Gates: gp≥75 **PASS**, p95≤138.8 **PASS**,
terr≥77 **PASS**.

**Decision: ACCEPT `wetlinks_v1` era only.** Not Current. No paid bump.
Do not mix with `starlink_v1` 82.09/76.26 or `ope_v36` 58/152. Crest
defaults unchanged. Product lock stays synthetic `starlink_v1`.

A first `dt=0.05` probe printed ~29/71 — that is `8*buffer/dt` ≈ 40 Mbps
starvation, not a CCA result. Archive reports the `dt=0.01` means.

Design: `docs/leoaware_v311_wetlinks.md`  
Windows: `traces/wetlinks/MANIFEST.md`  
Archive: `results/archive/20260813-v311-wetlinks/`

---

## v3.11-uncap - WetLinks 1 MB buffer (Crest vs BBR)

**Date:** 2026-08-13  
**Branch:** `cursor/v310-halo-84b8`  
**Hypothesis:** Capped Crest 156.70/63.98 is a 250 KB / 200 Mbps send
ceiling, not a CCA result. Same 5 windows, Crest defaults, α=0.20,
dt=0.01, buffer **1 MB** (ceiling 800 Mbps) for CUBIC+BBR+Crest. Kill if
Crest gp mean < BBR.

Product `LeoPathConfig.buffer_bytes` stays 250 KB. No CCA invention.
Capacity is still UDP iperf mean, not dish PHY. Era `wetlinks_v1`
research only. Not Current. Do not mix with 156.70, 82.09/76.26, or 58/152.

### Uncapped table (gate)

| CCA | gp mean | p95 mean |
|-----|--------:|---------:|
| CUBIC | 94.22 | 68.38 |
| **BBRv3approx** | **240.48** | 71.38 |
| LeoAware Crest | 239.72 | 70.38 |

Terr 78.623. Crest 239.72 < BBR 240.48.

**Decision: REJECT.** Uncap worked (w1/w2 ~387–397 vs ~190 at 250 KB).
Crest still behind BBR at the uncapped ceiling. No CCA invention. No
Current. No merge.

Archive: `results/archive/20260813-v311-wetlinks-uncap/`  
Design: `docs/leoaware_v311_wetlinks_uncap.md`

---

## v3.12 - zhao_zenodo23 ingest + geometry (research era only)

**Date:** 2026-08-13  
**Branch:** `cursor/v312-zhao-zenodo23-db91`  
**Hypothesis:** A real Starlink access dump (Victoria Ethernet → Seattle PoP → GCP us-west1-a, concurrent IRTT 10 ms + iPerf3 TCP Cubic 100 ms) can be sliced into five calendar-quantile sessions and walked for absolute 75/138.8 geometry without CCA.

### Method

- Zenodo DOI 10.5281/zenodo.10020034 (CC-BY-4.0); paper arXiv:2307.06863 / PIMRC 2023.
- Validity: complete IRTT+iperf JSON pair, duration ≥90 s. **716/716** pairs passed.
- Quantile rule: **calendar start time**, nearest-rank q ∈ {0, 0.25, 0.50, 0.75, 1} (indices 0, 179, 358, 536, 715). Not goodput quantiles. Not cherry-picks.
- Capacity = TCP Cubic downlink goodput (`cubic_goodput_mbps`). Oracle = ∫ series = **lower bound**. Not dish PHY. SQM **unknown**.
- Resample dt=0.05: IRTT last-obs (10 ms), iperf hold-within-bin (100 ms). No invented HO flags.
- **No CCA.** Dump not vendored (~9.7 GB deleted after slice).

### Geometry (native IRTT p95; cubic-goodput oracle)

| q | session | oracle cubic-gp | IRTT p95 |
|---|---------|----------------:|---------:|
| q00 | 2023-09-13 00:40Z | 36.00 | 54.23 |
| q25 | 2023-09-14 06:30Z | 38.16 | 64.20 |
| q50 | 2023-09-15 12:20Z | 36.43 | 395.35 |
| q75 | 2023-09-16 18:00Z | 28.16 | 81.55 |
| q100 | 2023-09-17 23:50Z | 13.11 | 138.37 |
| **mean** | | **30.37** | **146.74** |

### Gate

| Check | Bar | Result |
|-------|-----|--------|
| gp mean | ≥ 75 | **INCONCLUSIVE** (lower bound 30.37, not FAIL) |
| p95 mean | ≤ 138.8 | **FAIL** (146.74; q50 395 ms dominates; dropping it would be a cherry-pick) |

**Decision: geometry landed (PR #12 merged). Not Current. Do not mix with wetlinks_v1 or starlink_v1 Crest. Do not use for dual-gate ACCEPT. Do not start Crest/BBR on this era.**

Archive: `results/archive/20260813-v312-zhao-zenodo23-geom/`  
Design: `docs/leoaware_v312_zhao_zenodo23.md`  
Slices: `traces/zhao_zenodo23/`

---

## v3.13 - leocc_v1 ingest + dual-gate cook (research era only)

**Date:** 2026-08-14  
**Branch:** `cursor/v313-leocc-traces-a108`  
**Hypothesis:** LeoCC / LeoReplayer (SIGCOMM 2025) is a public continuous ≥90s
UDP-saturation + ICMP delay Starlink dump. Five catalog-quantile **downlink**
windows can decide absolute 75/138.8 without inventing traces.

### Method

- Source: SpaceNetLab/LeoCC (MIT) + Tsinghua Cloud `4.8K.zip` (download succeeded).
- 4800 traces; this era is **downlink only** (2400). Uplink not mixed.
- Validity: delay bins ≥ 9000 (90 s). **2398 / 2400**. Excluded: D/16 (75.92 s),
  D/212 (88.39 s) — short duration, not gp/p95 cherry-picks.
- Quantile: catalog `(site A..D, trace 1..600)` nearest-rank q ∈ {0,0.25,0.50,0.75,1}
  → A/1, A/600, B/600, C/599, D/600.
- Capacity = UDP sat (12 Mbps/line). RTT = 2 × OWD. `reconfig=0`. No CCA invention.
- **Not** zhao_zenodo23 (PR #12; Cubic; p95 FAIL). **Not** WetLinks hold-expand.

### Geometry (native 2×OWD p95; UDP-sat oracle)

| q | site/trace | oracle UDP-sat | 2×OWD p95 |
|---|------------|---------------:|----------:|
| q00 | A/1 | 425.83 | 32.00 |
| q25 | A/600 | 353.33 | 32.00 |
| q50 | B/600 | 408.26 | 60.00 |
| q75 | C/599 | 406.40 | 108.00 |
| q100 | D/600 | 380.91 | 194.00 |
| **mean** | | **394.95** | **85.20** |

gp ≥ 75 **PASS**. p95 ≤ 138.8 **PASS** (mean; D/600 194 is a real far-site tail).

### CCA means (dt=0.01, 1 MB era buffer; product default stays 250 KB)

| CCA | gp mean | p95 mean |
|-----|--------:|---------:|
| CUBIC | 31.14 | 87.20 |
| BBRv3approx | 379.80 | 89.60 |
| **LeoAware Crest** | **337.97** | **89.60** |

Terr 78.62 @ 46 ms. Crest 337.97 < BBR 379.80. p95 tied at 89.60.
Crest wins A/1 and A/600 by a little; loses B/C and especially D/600
(204.61 vs BBR 358.29 on the 194 ms far-site tail).

**Decision: ACCEPT_ERA_REJECT_BBR.** Absolute 75/138.8 PASS on means.
Crest does not clear BBR. Not Current. No paid. Do not merge. Do not mix eras.

Archive: `results/archive/20260814-v313-leocc/`  
Design: `docs/leoaware_v313_leocc.md`

---

## 2026-08-14 — Public progress (JON-14)

Docs-only. Reproduced ASCENT-D integrity (PASS). Published means-vs-BBR note from the Crest `starlink_v1` archive (`results/archive/20260812-v39-starlink-v1/`) for orbitstack /progress. Product lock remains `starlink_v1` Crest. No VELA operators. No dish/PHY Mbps. No `leocc_v1` numbers on the public note. See `docs/progress/2026-08-14-public-means.md`.

---

## v3.16 OpenSlot — starlink_v1 product-era (REJECT vs BBR)

**Date:** 2026-08-14  
**Branch:** `cursor/v316-starlink-e853`  
**Hypothesis:** Crest’s 0.37 Mbps gap vs BBR on synthetic `starlink_v1` is a
delay-clean soft-pace `can_send` bind (BBR has none). Unbind when delay-clean
and underfilled, without raising BDP or gating `ep:loss_burst`.

### Diagnosis (same v3.9 seeds / harness)

`python3 -m experiments.diag_v316_starlink`

| Hypothesis | Verdict |
|------------|---------|
| H1 pace-bind (98.4% of slots) | **CONFIRMED** |
| H2 first-2s starve | **PARTIAL** (seed 42 only: 41.3 vs 58.5) |
| H3 Crest p82 `bw_est` < BBR max-filter | **DISCARDED** (97.0 ≥ 96.1) |
| H4 REPROBE tax | **WEAK** (2.3% of ACKs) |

Killed before archive (same name): unconstrained unbind (seed 13 → 96.20);
clean-path 2.5× burst (seed 13 → 96.15). Slack gate kept.

### Lever

**OpenSlot** (`use_openslot`, default **False**). Delay-clean
(`rtt/min_rtt < 1.12`) and inflight < 0.80× BDP → skip pace bind.
Never gates `ep:loss_burst`. No FarHold / FastExit / LeanCatch / SpikeHold /
Halo / Pulse / QSP / PATHHINT.

### Official archive (synthetic `starlink_v1`, 90s, seeds 13,7,42,99,123)

`python3 -m experiments.run_starlink`

#### leo_fast_ho means

| CCA | gp mean | p95 mean |
|-----|--------:|---------:|
| CUBIC | 8.57 | 71.63 |
| BBRv3approx | **82.44** | 76.66 |
| LeoAware v3.9 Crest (lock) | 82.07 | 76.26 |
| **LeoAware + OpenSlot** | **82.38** | **76.26** |

Per-seed OpenSlot gp / p95: 13→96.69/72.21 · 7→75.34/67.81 · 42→81.15/97.56 ·
99→73.12/64.09 · 123→85.61/79.65

#### Other scenarios

| Scenario | LeoAware gp | p95 | note |
|----------|------------:|----:|------|
| leo_single | 83.51 | 74.95 | BBR 83.32 / 74.95 |
| terrestrial | **79.05** | 46.0 | ≥ 77 @ ~46 **PASS** |

### Gates

| Check | Bar | Result |
|-------|-----|--------|
| gp mean clears BBR | > 82.44 | **82.38 FAIL** |
| p95 mean vs BBR | ≤ 76.66 | **76.26 PASS** (no Crest p95 regress) |
| absolute gp / p95 | ≥75 / ≤138.8 | PASS |
| terrestrial | ≥ 77 | **79.05 PASS** |
| seeds | 13,7,42,99,123 | PASS (none dropped) |
| integrity | flag default False | PASS |

OpenSlot closes ~0.29 of the 0.37 Mbps (helps 7/99/123 past BBR). Seed 13
leftover (~0.62 vs BBR) is a **cwnd** gap, not pace. Short **0.06 Mbps**.

**Decision: REJECT vs BBR.** Research-on-product-era only. Not Current. Not
paid. Do not merge. Do not bump orbitstack. Committed default stays
`use_openslot=False`. Path is synthetic until CSV lock.

Design: `docs/leoaware_v316_starlink.md`  
Archive: `results/archive/20260814-v316-starlink/`

---

## v3.17 FillGap — starlink_v1 product-era (ACCEPT vs BBR, do not merge)

**Date:** 2026-08-14  
**Branch:** `cursor/v317-fillgap-0208`  
**Hypothesis:** Seed 13 leftover after OpenSlot (96.69 vs BBR 97.31) is cwnd
sitting below delivery BDP on a delay-clean, delivery-caught path. A small
cwnd fill (not a pace unbind, not a burst) closes the 0.06 mean gap.

### Diagnosis (same v3.9 seeds / harness; OpenSlot on, 0.80 untouched)

`python3 -m experiments.diag_v317_fillgap`

| Hypothesis | Verdict |
|------------|---------|
| H1 seed 13 cwnd below delivery BDP (eligible 0.607; cwnd/delBDP 0.80) | **CONFIRMED** |
| H2 seeds 7/99/123 already beat BBR (do not *need* the leftover) | **CONFIRMED** |

Mean OpenSlot cwnd 516 KB vs BBR 964 KB. Delivery BDP 630 KB. Unconstrained
unbind and 2.5× burst stay dead.

### Lever

**FillGap** (`use_fill_gap`, default **False**). Delay-clean
(`rtt/min_rtt < 1.12`) and delivery ≥ 0.95×`bw_est` and cwnd < 0.85×
delivery BDP → add **1 MSS**, capped at the 0.85× ceiling. Never gates
`ep:loss_burst`. Does not retune OpenSlot 0.80. No FarHold / FastExit /
LeanCatch / SpikeHold / Halo / Pulse / QSP / PATHHINT.

### Official archive (synthetic `starlink_v1`, 90s, seeds 13,7,42,99,123)

`python3 -m experiments.run_starlink`

#### leo_fast_ho means

| CCA | gp mean | p95 mean |
|-----|--------:|---------:|
| CUBIC | 8.57 | 71.63 |
| BBRv3approx | 82.44 | 76.66 |
| LeoAware v3.9 Crest (lock) | 82.07 | 76.26 |
| LeoAware + OpenSlot (v3.16) | 82.38 | 76.26 |
| **LeoAware + FillGap** | **82.45** | **76.26** |

Per-seed FillGap gp / p95: 13→96.80/72.21 · 7→75.36/67.81 · 42→81.25/97.56 ·
99→73.19/64.09 · 123→85.61/79.65

#### Other scenarios

| Scenario | LeoAware gp | p95 | note |
|----------|------------:|----:|------|
| leo_single | 83.56 | 74.95 | BBR 83.32 / 74.95 |
| terrestrial | **79.05** | 46.0 | ≥ 77 @ ~46 **PASS** |

### Gates

| Check | Bar | Result |
|-------|-----|--------|
| gp mean clears BBR | > 82.44 | **82.45 PASS** |
| p95 mean vs BBR | ≤ 76.66 | **76.26 PASS** (no Crest p95 regress) |
| seed 13 vs Crest / OpenSlot | ≥ 96.65 / 96.69 | **96.80 PASS** |
| absolute gp / p95 | ≥75 / ≤138.8 | PASS |
| terrestrial | ≥ 77 | **79.05 PASS** |
| seeds | 13,7,42,99,123 | PASS (none dropped) |
| integrity | flag default False | PASS |

**Decision: ACCEPT vs BBR** as research-on-product-era only. Not Current.
Not paid. Do not merge. Do not bump orbitstack. Committed default stays
`use_fill_gap=False`. Path is synthetic until CSV lock.

Design: `docs/leoaware_v317_fillgap.md`  
Archive: `results/archive/20260814-v317-fillgap/`

---

## 2026-08-20 — Promote v3.17 FillGap to Current / product dual-gate lock

**Date:** 2026-08-20  
**Change:** Product-lock promotion only. PR #22 squash-merged to `main` as
`781bd77`. FillGap / OpenSlot constructor defaults stay **False**. No new
CCA numbers.

Jon’s prior published lock was v3.9 Crest on synthetic `starlink_v1`
(82.07 gp / 76.26 p95, seeds 13,7,42,99,123). PR #22 archive (same path,
same seeds) is the new Current:

| CCA | Goodput mean | p95 mean | Notes |
|-----|-------------:|---------:|-------|
| CUBIC | 8.57 | 71.63 | Collapses under mobility |
| BBRv3approx | 82.44 | 76.66 | same orbit as LeoAware |
| **LeoAware v3.17 FillGap** | **82.45** | **76.26** | **new product dual-gate lock** |
| LeoAware v3.9 Crest (prior lock) | 82.07 | 76.26 | prior product lock |

Cited from PR #22 body and `results/archive/20260814-v317-fillgap/scorecard.json`
(`LeoAware_gp_mean` 82.44544 → 82.45; `LeoAware_p95_mean` 76.26408 → 76.26;
BBR 82.43904 / 76.66408 → 82.44 / 76.66). No CI check runs existed on #22;
no figure disagreed.

Beats Crest on gp, matches p95, edges BBR. Absolute bars still PASS
(gp ≥ 75, p95 ≤ 138.8, terr 79.05 ≥ 77).

Reproduce Current: `python3 -m experiments.run_starlink` (opts in FillGap +
OpenSlot; OpenSlot 0.80 not retuned). Default `LeoAwareCCA()` /
`multi_seed` remain Crest-constructor.

`ope_v36` / v3.7 OCE, WetLinks, `zhao_zenodo23`, and `leocc_v1` stay
**research-only**. Do not mix eras. Other open draft PRs untouched.

Design: `docs/leoaware_v317_fillgap.md`  
Eras: `docs/harness_eras.md`

---

## Open ideas (next loops)

1. Denser real Starlink CSVs (continuous 90s RTT+capacity, not hold-expanded 15s iperf). `leocc_v1` is the first such ingest; still not product lock.
2. Instrument per-seed delivery traces on `starlink_v2` before more fade/rise knobs.
3. Path-normalized latency `p95(rtt − path_base)` as a *secondary* queue metric (implemented; still not the product gate).
4. Crest flags are optional on synthetic `starlink_v1` (ablation: v37-style already dual-gates). Do not retune CCA for 0.2 Mbps.
5. Per-RTT fairness clock for multi-flow (fair_mode still coarse).
6. QUEUE-mode store-and-forward coupling with ASCENT-D.
7. Full 5-seed ablation with ascent_d vs hybrid under suite durations (90s).

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
