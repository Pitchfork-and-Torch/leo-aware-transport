# v3.11 WetLinks uncap (1 MB buffer)

**Era:** `wetlinks_v1` research only. **Not Current. Not paid. Do not merge.**  
**CCA:** v3.9 Crest defaults (endpoint-only). No Halo / QSP / PATHHINT.  
Soft-QIR α frozen 0.20. Product lock stays synthetic `starlink_v1`.

## Hypothesis

The capped 250 KB WetLinks table (Crest 156.70 / 63.98, BBR 161.91) is a
**buffer/dt ceiling**, not a CCA result. At `dt=0.01`, 250 KB caps send at
200 Mbps, so w1/w2 (~400 Mbps UDP iperf means) sit at ~190. Raise the
bottleneck buffer to **1 MB** (send ceiling 800 Mbps ≥ 450) for CUBIC, BBR,
and Crest on the **same five windows**. Then ask whether Crest clears BBR.

## What changed

- `experiments/run_wetlinks.py`: `WETLINKS_BUFFER_BYTES = 1_000_000` on
  WetLinks replay only.
- `LeoPathConfig.buffer_bytes` default stays **250_000** (product /
  terrestrial control).
- No CCA knobs. No denser fake traces. No LENS dumps.

## Gate (this table only)

Kill / **REJECT** if Crest gp mean **<** BBR gp mean at the uncapped
ceiling. Report p95 honestly. Do **not** mix with capped 156.70/63.98,
`starlink_v1` 82.09/76.26, or `ope_v36` 58/152.

Capacity is still UDP iperf download mean, not dish PHY. Windows are still
hold-expanded 15 s cycles.

```bash
python3 -m experiments.test_wetlinks_integrity
python3 -m experiments.run_wetlinks --tag 20260813-v311-wetlinks-uncap
```

Archive: `results/archive/20260813-v311-wetlinks-uncap/`
