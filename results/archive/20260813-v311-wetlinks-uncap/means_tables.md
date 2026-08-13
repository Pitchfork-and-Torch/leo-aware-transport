# v3.11 WetLinks uncap — 1 MB buffer

Same five windows as `20260813-v311-wetlinks`. Gate is **this** table.
Capped 250 KB (Crest 156.70/63.98) is a footnote only — do not mix.

| | buffer | send ceiling at dt=0.01 |
|--|-------:|------------------------:|
| product / capped footnote | 250 KB | 200 Mbps |
| **this cook** | **1 MB** | **800 Mbps** |

CCA means land after `python3 -m experiments.run_wetlinks --tag 20260813-v311-wetlinks-uncap`.
REJECT if Crest gp mean < BBR. No Current. No merge.
