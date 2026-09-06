# v3.20 detect over-fire — synthetic starlink_v1

FillGap + OpenSlot on. SoftCeil off. Duration 90s.
Official dual-gate: gp ≥ 75 / p95 ≤ 138.8.
Current stays v3.17 FillGap. SoftCeil stays REJECT. Not paid.

| seed | FG gp | BBR gp | p95 | path HO | detect | on_loss | fusion | near HO | far HO | far frac | HO recall |
|-----:|------:|-------:|----:|--------:|-------:|--------:|-------:|--------:|-------:|---------:|----------:|
| 13 | 96.80 | 97.31 | 72.21 | 7 | 56 | 53 | 3 | 11 | 45 | 0.804 | 1.000 |
| 7 | 75.36 | 75.08 | 67.81 | 8 | 56 | 51 | 5 | 15 | 41 | 0.732 | 1.000 |
| 42 | 81.25 | 81.25 | 97.56 | 7 | 56 | 50 | 6 | 14 | 42 | 0.750 | 1.000 |
| 99 | 73.19 | 72.98 | 64.09 | 7 | 56 | 50 | 6 | 13 | 43 | 0.768 | 1.000 |
| 123 | 85.61 | 85.57 | 79.65 | 8 | 57 | 54 | 3 | 12 | 45 | 0.789 | 1.000 |

Means: gp 82.45 · p95 76.26 · detect/HO 7.625 ·
far frac 0.768609022556391 · HO recall 1.0.
BBR 82.44 / 76.66.

| Check | Bar | Result |
|-------|-----|--------|
| official gp | ≥ 75 | 82.45 PASS |
| official p95 | ≤ 138.8 | 76.26 PASS |
| beats FillGap lock | > 82.45 and p95 ≤ 76.26 | NO — do not bump Current |

H4 most detects far from path HO: True
H5 tighter gate keeps HO / cuts far: WEAK
H6 one primary owns half of far: True
Promising shadow gates: []
Reason counts: {'loss_burst': 258, 'loss_rtt': 23, 'rtt_mad': 23, 'ack_ia': 20}
Source counts: {'on_loss': 258, 'fusion': 23}

Legal shadow gates (score 1.85/2.0, multi-reason, RTT-anchor) do not cut the over-fire. on_loss loss_burst is 258 events vs fusion 23; far fires are loss_burst, and ep:loss_burst stays ungated. Fusion already sits on real path HOs. Observe-only: do not cook a fusion-threshold raise, do not retry SoftCeil, do not bump Current. Next cook, if any, needs a new mobility-loss taxonomy — or leave detect alone.
