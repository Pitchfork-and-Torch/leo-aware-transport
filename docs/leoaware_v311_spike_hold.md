# v3.11-SH — spike-hold on uncapped WetLinks

**Era:** `wetlinks_v1` research. **Not Current. Not paid. Do not merge.**  
Product Crest keeps `use_spike_hold=False`. No Halo / QSP / PATHHINT.

## Hypothesis

Uncap REJECT left Crest **239.72 < BBR 240.48**. The leftover is mostly
w1 (−2.26 Mbps): Crest full-REPROBEs the inferred 0.4 s `ping_worst` spike
at t=12 while UDP capacity is **held flat**. BBR keeps its max-filter.

**Spike-hold:** if an endpoint RTT-jump detect fires and live delivery is
still ≥ 0.90× `bw_est`, skip full REPROBE for 0.50 s. Never skip
`ep:loss_burst`. Do not update `last_reconfig_t`.

## Gate

Same 5 windows, 1 MB buffer, dt=0.01, α=0.20. ACCEPT only if LeoAware+SH
gp mean **>** BBR. Else REJECT. Do not mix with 239.72/240.48 or 156.70.

```bash
python3 -m experiments.run_wetlinks --tag 20260814-v311-wetlinks-sh
```
