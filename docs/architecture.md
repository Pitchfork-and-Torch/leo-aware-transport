# Architecture

## Layers

```
+---------------------------+
|  experiments/run_suite    |  scenarios, CSV, plots
+---------------------------+
|  metrics + plotting       |  aggregate + visualize
+---------------------------+
|  sim.run_sim              |  multi-flow slot loop
+---------------------------+
|  ccas (CUBIC/BBR/LeoAware)|  sender-side CCA modules
+---------------------------+
|  network.LeoPath          |  LEO path dynamics
+---------------------------+
```

## Simulation loop (per slot `dt_s`)

1. Advance `LeoPath` (maybe trigger handover).
2. Optional path hint to CCA (`on_path_hint`).
3. Deliver due ACKs -> `on_ack(rtt, bytes)`.
4. Drain bottleneck by current capacity; apply mobility loss or enqueue ACK.
5. Each flow sends up to cwnd room (and soft per-slot cap); buffer overflow -> congestive `on_loss`.
6. Sample logs every 50 ms.

## CCA interface (QUIC-port friendly)

```python
class BaseCCA:
    def on_ack(self, t, rtt_s, bytes_acked, lost=0): ...
    def on_loss(self, t, bytes_lost, congestive: bool): ...
    def on_path_hint(self, t, reconfigured: bool): ...  # optional
    def can_send(self, t) -> int: ...  # bytes allowed
    def on_sent(self, n): ...
    def state(self) -> CCAState: ...
```

A real quiche / picoquic controller would map:

- ACK frames -> `on_ack`
- loss detection (and ECN) -> `on_loss` with congestive heuristic
- optional path challenge / network signal -> `on_path_hint`

## Why slot-based (not full discrete event)

Enough fidelity for CCA research under LEO dynamics, minimal deps, fast suite runs, easy to teach. Can be replaced with an event queue later without changing CCA modules.

## Fairness in evaluation

LeoAware defaults to **endpoint-only** detection (`use_path_hints=False`). Baselines never receive privileged reconfiguration signals. That keeps the comparison honest for the "no network cooperation" claim.

v3.6+ **OPE:** mobility loss uses a dedicated `loss_rng`, so a CCA cannot rewrite the HO/RTT/cap timeline. v3.8 Step 0 **freezes** soft-QIR α=0.20. ACK logs include path-base RTT so `p95(rtt − path_base)` is a secondary diagnostic — it does not replace absolute ACK p95.

v3.9 **eras:** `ope_v36` is the research relative-BBR path (**Current = v3.7 OCE**);
**`starlink_v1` is the product-lock default** for `multi_seed` / `run_suite`
(v3.9 scorecard 82.07 / 76.26 — not a Current bump). Never mix eras in a
Current hero table (`docs/harness_eras.md`).
