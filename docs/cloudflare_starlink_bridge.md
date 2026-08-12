# Cloudflare x Starlink collaboration bridge

How this prototype could seed real work between a protocol-heavy edge network and a LEO operator.

## Why these two parties

- **Cloudflare** owns high-volume QUIC (quiche), congestion research culture, and global PoPs that terminate eyeball traffic including Starlink.
- **Starlink** owns the LEO topology: handovers, beams, ISLs, capacity maps, and potential path-change signals.

Neither alone closes the loop: endpoints misread mobility without good signals; the network cannot fix every app stack without endpoint participation.

## Phased path

### Phase 0 - This repo

- Shared vocabulary and metrics.
- Endpoint detection + re-probe logic under synthetic LEO dynamics.
- A/B experiment design templates (LEO vs terrestrial, multi-flow fairness).

### Phase 1 - Measurement

- Instrument Starlink-attached clients or Cloudflare PoPs for RTT jump, loss burst, and goodput around known handover windows.
- Validate which endpoint signals fire before / during / after reconfig.
- Replay anonymized traces into `LeoPath` or a richer simulator.

### Phase 2 - Endpoint deploy (Cloudflare)

- Port LeoAware controller interface into quiche (or a shadow controller).
- A/B: CUBIC / BBR vs LeoAware for Starlink ASN / known satellite paths.
- Keep `use_path_hints=False` until signals exist.

### Phase 3 - Optional signaling (Starlink + edge)

- Lightweight reconfiguration / epoch markers (not full ephemeris required).
- Feed `on_path_hint` to cut detection lag and false positives.
- Privacy and spoofing design: authenticated path-change tokens where possible.

### Phase 4 - Multipath and AI-scale

- Dual ground-station / dual-PoP multipath for long-lived bulk (model weights, sync).
- Interactive vs bulk policy differentiation under LEO latency variance.
- ISL-aware scheduling when optical mesh routes change mid-flow.

## Integration points (quiche-oriented)

```
QUIC sender
  -> on_ack / loss detection  -> LeoAwareCCA
  -> pacing / cwnd            <- CCA state
  -> optional PATH_HINT frame or side channel from edge/Starlink
```

The CCA module in `leo_cc/ccas.py` is intentionally small and side-effect free beyond its internal estimates.

## Success metrics for a real pilot

- Goodput under high handover intensity
- p95 / p99 latency and rebuffer rates for interactive traffic
- Retransmit rate split: mobility-tagged vs congestion-tagged
- Fairness under multi-flow LEO cells
- No large terrestrial regression
