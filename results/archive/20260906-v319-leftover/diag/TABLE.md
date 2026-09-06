# v3.19 leftover observability — synthetic starlink_v1

FillGap + OpenSlot on. SoftCeil off. Duration 90s.
Current stays v3.17 FillGap. Not paid.

| seed | FG gp | BBR gp | path HO | detect | cruise band | post-detect band | real-HO band |
|-----:|------:|-------:|--------:|-------:|------------:|-----------------:|-------------:|
| 13 | 96.80 | 97.31 | 7 | 56 | 0.030 | 0.177 | 0.020 |
| 7 | 75.36 | 75.08 | 8 | 56 | 0.029 | 0.164 | 0.020 |
| 42 | 81.25 | 81.25 | 7 | 56 | 0.022 | 0.131 | 0.018 |
| 99 | 73.19 | 72.98 | 7 | 56 | 0.032 | 0.171 | 0.022 |
| 123 | 85.61 | 85.57 | 8 | 57 | 0.024 | 0.166 | 0.014 |

Means: leftover band cruise 0.027 ·
post-detect 0.162 ·
real path HO 0.019.
Detect / path HO 8.028571428571428.
Post-detect ACK share 0.860
(inflated if detect over-fires). Real path-HO ACK share
0.107.

H1 post-detect vs cruise: True
H2 detect over-fire: True
H3 leftover band in real HO: False
H3b below-0.85 in real HO: True
