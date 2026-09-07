# v3.21 on_loss / ep:loss_burst taxonomy — synthetic starlink_v1

FillGap + OpenSlot on. SoftCeil off. Duration 90s.
Official dual-gate: gp ≥ 75 / p95 ≤ 138.8.
Current stays v3.17 FillGap. SoftCeil stays REJECT. Not paid.

| seed | FG gp | BBR gp | p95 | path HO | on_loss-only HO | far on_loss | far cluster2 | far pace | suppressed |
|-----:|------:|-------:|----:|--------:|----------------:|------------:|-------------:|---------:|-----------:|
| 13 | 96.80 | 97.31 | 72.21 | 7 | 4 | 45 | 3 | 37 | 2291 |
| 7 | 75.36 | 75.08 | 67.81 | 8 | 3 | 41 | 4 | 30 | 2100 |
| 42 | 81.25 | 81.25 | 97.56 | 7 | 1 | 42 | 12 | 31 | 2130 |
| 99 | 73.19 | 72.98 | 64.09 | 7 | 1 | 43 | 5 | 33 | 1825 |
| 123 | 85.61 | 85.57 | 79.65 | 8 | 5 | 45 | 4 | 40 | 2127 |

Means: gp 82.45 · p95 76.26 · detect/HO 7.625 ·
far frac 0.768609022556391 · HO recall 1.0.
BBR 82.44 / 76.66.
Far on_loss 216 · cluster-2 28 ·
pacemaker 171 · on_loss-only HO 14 ·
fusion-covered HO 23.

| Check | Bar | Result |
|-------|-----|--------|
| official gp | ≥ 75 | 82.45 PASS |
| official p95 | ≤ 138.8 | 76.26 PASS |
| beats FillGap lock | > 82.45 and p95 ≤ 76.26 | NO — do not bump Current |

H7 far on_loss is pacemaker: True
H8 taxonomy keeps HO / cuts far: RECKLESS
H9 some HO on_loss-only: True
Promising taxonomy gates: []

Far on_loss is the 1.4s pacemaker, but some path HOs are covered only by on_loss (fusion miss). Legal taxonomy shadows that cut the leftover also drop those hops. REJECT a live loss-burst gate. Leave detect alone. Do not bump Current.
