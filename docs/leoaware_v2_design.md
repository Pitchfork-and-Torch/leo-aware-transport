# LeoAware v2 design notes

## What changed (and why)

### 1. Detection robustness (multi-signal fusion)

**Before:** Fixed RTT median/p25 ratios and ACK inter-arrival heuristics.

**Now:**
- Robust **MAD z-scores** on RTT and ACK inter-arrival (LeoCC-style response-interval family)
- **EWMA** RTT mean/variance for adaptive absolute floors
- **Delivery-rate collapse** vs rate EWMA (capacity freeze / hop)
- **Mobility loss bursts** without RTT inflation
- Fusion **score threshold** with classic absolute RTT jump as a high-precision solo trigger
- **Cooldown** to limit double-fire while allowing strong signals through

**Expected benefit:** Fewer false positives under noise; still catches abrupt LEO hops. Cost: O(1) deque stats per ACK.

### 2. Post-reconfig recovery (two-phase REPROBE)

**Before:** Single soft cut (~0.55x) + uniform growth for a fixed hold.

**Now:**
- Soft cut retained (anti-CUBIC philosophy)
- **Phase A explore** then **Phase B fill** with higher growth
- Soft **prior BDP** only as ceiling scale (not trusted samples across epochs)
- **Early exit** when RTT variance stabilizes and bandwidth samples exist
- Soft pacing that does **not** starve recovery (hard pacing was measured to hurt goodput)

Inspired by BBR's delivery-rate model for fill, without keeping stale min-RTT across epochs (BBR LEO failure mode). Soft alternative to SaTCP hard freeze.

### 3. Predictive / ASCENT-aware control

`on_path_hint(t, reconfigured, *, capacity_bps=, rtt_s=, epoch=)`:
- When `use_path_hints=True`, reconfig triggers REPROBE with **predicted capacity/RTT** as a soft start
- Optional capacity blend into `bw_est` after hop
- Endpoint-only path remains default (`use_path_hints=False`) for fair suite eval

Simulator passes capacity/RTT/epoch on reconfig events (safe no-ops for baselines).

### 4. Multi-flow / coexistence

- Bandwidth estimate at **~78th percentile** (less greedy than BBR max-filter)
- Mild **delay_yield** when RTT >> min_RTT (queue building)
- Congestive cut ~0.72x (slightly gentler than classic 0.7 CUBIC-class)

### 5. Production hooks

- `on_ecn(t, ce_count)` mild backoff (ignored immediately after mobility)
- Soft **pacing rate** exposed in `state().pacing_rate_bps` for quiche-style ports
- Interface preserved: `on_ack` / `on_loss` / `on_path_hint` / `can_send`

## Suite results (after v2)

Same harness seeds/scenarios as v1 README baseline.

| Scenario | CCA | Goodput Mbps | p95 RTT ms | vs LeoAware v1 |
|----------|-----|-------------:|-----------:|----------------|
| leo_fast_ho | CUBIC | 6.44 | 134.3 | |
| leo_fast_ho | BBRv3approx | 65.38 | 188.6 | |
| leo_fast_ho | **LeoAware v2** | **70.36** | **123.2** | was 68.3 / 164 |
| leo_single | CUBIC | 9.04 | 111.2 | |
| leo_single | BBRv3approx | 83.99 | 161.8 | |
| leo_single | **LeoAware v2** | **81.97** | **141.1** | was 64.7 / 129 |
| terrestrial | BBRv3approx | 78.81 | 40.0 | |
| terrestrial | **LeoAware v2** | **77.39** | **40.0** | was 78.0 (no material LEO-only regression) |

**Read:** Under fast handovers, v2 improves both goodput and p95 vs v1 and dominates the BBR approx latency-goodput tradeoff. On calmer single-flow LEO, v2 closes most of the goodput gap to BBR while keeping better p95 than BBR. Terrestrial stays competitive.

Multi-flow Jain remains a research open (mean goodput high variance across flows); v2 did not fully solve coexistence under aggressive LEO multi-sender stress.

## Remaining risks

- Slot-based sim fidelity (not real QUIC / Starlink traces)
- Detection still heuristic; rare false positives under heavy delay noise
- Multi-flow fairness needs dedicated work (maybe per-flow pacing + RTT fairness)
- ASCENT rich telemetry (altitude windows, QUEUE mode) still partial

## quiche port sketch

Map:
- ACK receipt -> `on_ack(now, latest_rtt, bytes)`
- Loss detection -> `on_loss(now, bytes, congestive=is_persistent_congestion || ecn_heavy)`
- Path challenge / custom FRAME or side channel -> `on_path_hint(..., capacity_bps=..., rtt_s=...)`
- Send loop: `min(can_send(now), pacing_budget)` using `state().pacing_rate_bps`

## Reproduce

```bash
pip install -r requirements.txt
python -m experiments.run_suite
# results/summary.csv
```
