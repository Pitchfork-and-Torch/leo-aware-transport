#!/usr/bin/env python3
"""SkyPulse PATHHINT hybrid vs endpoint (growth-freeze only).

Public suite / multi_seed stay endpoint-only. This cook measures assist
separately via existing ASCENT-D ingest (no second ingest path).

  python -m experiments.run_skypulse
  python -m experiments.run_skypulse --tag 20260813-v310-skypulse
"""
from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from leo_cc.ccas import BbrCCA, LeoAwareCCA
from leo_cc.harness import (
    PRODUCT_GP_BAR,
    PRODUCT_P95_BAR,
    PRODUCT_PATH_PROFILE,
    PRODUCT_TERR_GP_BAR,
    apply_profile,
    resolve_path_profile,
)
from leo_cc.metrics import summarize_result
from leo_cc.network import LeoPathConfig
from leo_cc.sim import SOFT_QIR_ALPHA, run_sim

RESULTS = ROOT / "results"

CREST_GP = 82.089
CREST_P95 = 76.264
CREST_TERR_GP = 78.623


def _row(scenario: str, seed: int, cca: str, m, n_ho: int, applied: int = 0) -> dict:
    return {
        "scenario": scenario,
        "seed": seed,
        "cca": cca,
        "goodput_mbps": m.goodput_bps / 1e6,
        "p95_rtt_ms": m.p95_rtt_s * 1000,
        "p95_path_rtt_ms": m.p95_path_rtt_s * 1000,
        "p95_excess_rtt_ms": m.p95_excess_rtt_s * 1000,
        "loss_rate": m.loss_rate,
        "handovers": n_ho,
        "ascent_applied": applied,
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--seeds", default="13,7,42,99,123")
    ap.add_argument("--tag", default="20260813-v310-skypulse")
    ap.add_argument("--path-profile", default=PRODUCT_PATH_PROFILE)
    args = ap.parse_args()
    path_profile = resolve_path_profile(args.path_profile)
    seeds = [int(x) for x in args.seeds.split(",") if x.strip()]

    print(
        f"skypulse era={path_profile}  α={SOFT_QIR_ALPHA}  "
        f"Crest baseline {CREST_GP}/{CREST_P95}",
        flush=True,
    )

    rows = []
    for seed in seeds:
        cfg = apply_profile(
            LeoPathConfig(
                duration_s=90,
                handover_interval_s=12,
                handover_jitter_s=4,
                seed=seed,
            ),
            path_profile,
        )
        for label, factory, kw in (
            ("endpoint", lambda: LeoAwareCCA(), dict(path_hint_mode="none")),
            (
                "hybrid",
                lambda: LeoAwareCCA(
                    use_path_hints=True,
                    hint_freeze_only=True,
                    use_orb_signals=False,
                ),
                dict(path_hint_mode="ascent_d", ascent_bit_flips=0),
            ),
            ("BBRv3approx", BbrCCA, dict(path_hint_mode="none")),
        ):
            print(f"leo_fast_ho seed={seed} {label} ...", flush=True)
            res = run_sim(factory, cfg=cfg, n_flows=1, **kw)
            m = summarize_result(res)[0]
            applied = res.ascent_ingest.applied if res.ascent_ingest else 0
            rows.append(_row("leo_fast_ho", seed, label, m, len(res.handovers), applied))
            print(
                f"  gp={m.goodput_bps/1e6:.2f} p95={m.p95_rtt_s*1000:.2f} "
                f"applied={applied}",
                flush=True,
            )

        tcfg = LeoPathConfig(duration_s=60, seed=seed, terrestrial=True)
        for label, factory, kw in (
            ("endpoint", lambda: LeoAwareCCA(), dict(path_hint_mode="none")),
            (
                "hybrid",
                lambda: LeoAwareCCA(
                    use_path_hints=True,
                    hint_freeze_only=True,
                    use_orb_signals=False,
                ),
                dict(path_hint_mode="ascent_d", ascent_bit_flips=0),
            ),
        ):
            print(f"terrestrial seed={seed} {label} ...", flush=True)
            res = run_sim(factory, cfg=tcfg, n_flows=1, **kw)
            m = summarize_result(res)[0]
            applied = res.ascent_ingest.applied if res.ascent_ingest else 0
            rows.append(_row("terrestrial", seed, label, m, 0, applied))

    df = pd.DataFrame(rows)
    out = RESULTS / "archive" / args.tag
    out.mkdir(parents=True, exist_ok=True)
    df.to_csv(out / "skypulse_raw.csv", index=False)

    def means(scen: str, cca: str) -> tuple[float, float]:
        sub = df[(df["scenario"] == scen) & (df["cca"] == cca)]
        return float(sub["goodput_mbps"].mean()), float(sub["p95_rtt_ms"].mean())

    ep_gp, ep_p95 = means("leo_fast_ho", "endpoint")
    hy_gp, hy_p95 = means("leo_fast_ho", "hybrid")
    bbr_gp, bbr_p95 = means("leo_fast_ho", "BBRv3approx")
    ep_t, ep_tp = means("terrestrial", "endpoint")
    hy_t, hy_tp = means("terrestrial", "hybrid")

    def pareto(gp: float, p95: float, base_gp: float, base_p95: float) -> bool:
        gp_up = gp > base_gp + 1e-6 and p95 <= base_p95 + 1e-6
        p95_dn = p95 < base_p95 - 1e-6 and gp >= base_gp - 1e-6
        return bool(gp_up or p95_dn)

    # 0.02 Mbps / 0.05 ms: rounding vs published Crest 82.09/76.26, not a real miss
    ep_ok = (
        (not math.isnan(ep_gp))
        and ep_gp + 0.02 >= CREST_GP
        and ep_p95 <= CREST_P95 + 0.05
    )
    hy_abs = hy_gp >= PRODUCT_GP_BAR and hy_p95 <= PRODUCT_P95_BAR and hy_t >= PRODUCT_TERR_GP_BAR
    hy_pareto = pareto(hy_gp, hy_p95, CREST_GP, CREST_P95)
    accept = bool(ep_ok and hy_abs and hy_pareto)
    card = {
        "era": path_profile,
        "cook": "v3.10 SkyPulse PATHHINT growth-freeze",
        "soft_qir_alpha": SOFT_QIR_ALPHA,
        "ingest": "ascent_d (existing leo_cc.ascent_path_hint)",
        "hint_policy": "growth-freeze only; never gate ep:loss_burst",
        "public_suite": "endpoint-only (unchanged)",
        "crest_baseline": {"gp": CREST_GP, "p95": CREST_P95, "terr_gp": CREST_TERR_GP},
        "endpoint": {
            "gp_mean": ep_gp,
            "p95_mean": ep_p95,
            "terr_gp_mean": ep_t,
            "terr_p95_mean": ep_tp,
            "no_regression_vs_crest": ep_ok,
        },
        "hybrid": {
            "gp_mean": hy_gp,
            "p95_mean": hy_p95,
            "terr_gp_mean": hy_t,
            "terr_p95_mean": hy_tp,
            "pareto_vs_crest": hy_pareto,
        },
        "bbr": {"gp_mean": bbr_gp, "p95_mean": bbr_p95},
        "gates": {
            "endpoint_no_regression": ep_ok,
            "hybrid_gp_ge_75": hy_gp >= PRODUCT_GP_BAR,
            "hybrid_p95_le_138_8": hy_p95 <= PRODUCT_P95_BAR,
            "hybrid_terr_ge_77": hy_t >= PRODUCT_TERR_GP_BAR,
            "hybrid_pareto_vs_crest": hy_pareto,
        },
        "decision": "ACCEPT" if accept else "REJECT",
        "note": (
            "ACCEPT only if hybrid Pareto vs Crest AND endpoint not worse than Crest. "
            "Not Current. No paid. Do not merge."
        ),
    }
    (out / "scorecard.json").write_text(json.dumps(card, indent=2), encoding="utf-8")
    print("\n=== SkyPulse scorecard ===")
    print(json.dumps(card, indent=2))
    print(f"\nWrote {out}")


if __name__ == "__main__":
    main()
