# v3.4.1 code delta (LeoAwareCCA in leo_cc/ccas.py)

## Lever
Cruise `delay_yield` subtract at `delay_ratio > 1.45`: **0.35 → 0.25 MSS**.

## Diff vs tip v3.4-p95 (8442b1c / blob d476853)
```diff
@@ LeoAwareCCA docstring @@
+    v3.4.1 overnight (ablation winner; gp floor 75 still miss):
+      - Mild delay_yield subtract 0.35→0.25 MSS at delay_ratio>1.45
+      - Large multi-seed sweep: fill/detect/cruise relaxations failed Pareto
+      - Best locked: ~73.9 gp / ~128 p95 (p95 gate PASS; gp≥75 FAIL)
+      - No DTCE / EpochMemory / detect-threshold changes

@@ on_ack cruise delay_yield @@
-                # Early mild yield (v3.3-A only acted above 2.0)
-                self.cwnd = max(4 * MSS, self.cwnd - MSS * 0.35)
+                # v3.4.1: milder yield subtract (0.35→0.25); keeps p95 gate, +gp
+                self.cwnd = max(4 * MSS, self.cwnd - MSS * 0.25)
```

## Locked multi-seed (tag 20260812-p95-reclaim-v341, seeds 13,7,42,99,123, 90s)
| CCA | gp mean | p95 mean |
|-----|--------:|---------:|
| BBRv3approx | 70.88 | 138.8 |
| LeoAware v3.4 tip | 73.57 | 138.37 |
| LeoAware v3.4.1 | 73.92 | 128.15 |
| terrestrial LeoAware | 78.20 | 40.0 |

**Accept bar: REJECT/WIP** — p95≤138.8 PASS, terr≥77 PASS, gp≥75 FAIL (~1.08 Mbps short).
