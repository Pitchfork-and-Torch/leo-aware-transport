#!/usr/bin/env python3
"""v3.18 diagnosis: seed 13 leftover after FillGap is a 0.85-ceiling bind?

Same rails as the v3.17 FillGap lock: leo_fast_ho 90s, seeds 13,7,42,99,123,
synthetic starlink_v1, soft-QIR α=0.20, endpoint-only. FillGap + OpenSlot on
(0.85 / 0.80 not retuned).

Measures whether delay-clean, delivery-caught ACKs sit in the leftover
band [0.85×, 0.90×) delivery BDP after FillGap has already filled to 0.85.

Does not change CCA defaults.

Usage:
  python3 -m experiments.diag_v318_softceil
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from leo_cc.ccas import BbrCCA, LeoAwareCCA
from leo_cc.harness import PRODUCT_PATH_PROFILE, PRODUCT_SEEDS, apply_profile
from leo_cc.metrics import summarize_result
from leo_cc.network import LeoPathConfig
from leo_cc.sim import SOFT_QIR_ALPHA, run_sim

OUT = ROOT / "results" / "archive" / "20260904-v318-softceil" / "diag"

FILLGAP_SEED13_GP = 96.80
FILLGAP_GP_LOCK = 82.45


class DiagFillGap(LeoAwareCCA):
    """Count SoftCeil-eligible ACKs on the FillGap lock. No control change."""

    def __init__(self, **kw):
        kw.setdefault("use_openslot", True)
        kw.setdefault("use_fill_gap", True)
        kw.setdefault("use_soft_ceil", False)
        super().__init__(**kw)
        self.diag_acks = 0
        self.diag_delay_clean = 0
        self.diag_delivery_caught = 0
        self.diag_below_085 = 0
        self.diag_in_leftover_band = 0
        self.diag_softceil_eligible = 0
        self.diag_at_or_above_090 = 0
        self.diag_cwnd_sum = 0.0
        self.diag_del_bdp_sum = 0.0
        self.diag_del_sum = 0.0
        self.diag_bw_sum = 0.0
        self.diag_n_rate = 0

    def on_ack(self, t: float, rtt_s: float, bytes_acked: int, lost: int = 0) -> None:
        super().on_ack(t, rtt_s, bytes_acked, lost)
        self.diag_acks += 1
        delay = (
            (rtt_s / self.min_rtt)
            if self.min_rtt < 1e17 and self.min_rtt > 0
            else 99.0
        )
        delay_clean = (
            delay < 1.12
            and self.high_delay_streak == 0
            and t >= self.reprobe_until
            and t >= self._ca_hold_until
        )
        rate = self._delivery_rate_sample(t)
        caught = rate > 0 and self.bw_est > 1e6 and rate >= 0.95 * self.bw_est
        rtt_ref = self.min_rtt if self.min_rtt < 1e17 else 0.0
        del_bdp = rate * rtt_ref / 8.0 if rate > 0 and rtt_ref > 0 else 0.0
        if delay_clean:
            self.diag_delay_clean += 1
        if caught:
            self.diag_delivery_caught += 1
        if del_bdp > 0:
            ratio = self.cwnd / del_bdp
            if ratio < 0.85:
                self.diag_below_085 += 1
            elif ratio < 0.90:
                self.diag_in_leftover_band += 1
            else:
                self.diag_at_or_above_090 += 1
            if delay_clean and caught and 0.85 <= ratio < 0.90:
                self.diag_softceil_eligible += 1
        if rate > 0 and self.bw_est > 0:
            self.diag_del_sum += rate
            self.diag_bw_sum += self.bw_est
            self.diag_cwnd_sum += self.cwnd
            self.diag_del_bdp_sum += del_bdp
            self.diag_n_rate += 1


class DiagBbr(BbrCCA):
    def __init__(self, **kw):
        super().__init__(**kw)
        self.diag_cwnd_sum = 0.0
        self.diag_n = 0

    def on_ack(self, t: float, rtt_s: float, bytes_acked: int, lost: int = 0) -> None:
        super().on_ack(t, rtt_s, bytes_acked, lost)
        if self.bw_est > 0 and self.min_rtt < 1e17:
            self.diag_cwnd_sum += self.cwnd
            self.diag_n += 1


def _cfg(seed: int) -> LeoPathConfig:
    return apply_profile(
        LeoPathConfig(
            duration_s=90,
            handover_interval_s=12,
            handover_jitter_s=4,
            seed=seed,
        ),
        PRODUCT_PATH_PROFILE,
    )


def _mean(xs: list[float]) -> float:
    return sum(xs) / len(xs) if xs else float("nan")


def run_seed(seed: int) -> dict:
    leo_box: dict = {}
    bbr_box: dict = {}

    def leo_factory():
        c = DiagFillGap()
        leo_box["cca"] = c
        return c

    def bbr_factory():
        c = DiagBbr()
        bbr_box["cca"] = c
        return c

    lres = run_sim(leo_factory, cfg=_cfg(seed), n_flows=1)
    bres = run_sim(bbr_factory, cfg=_cfg(seed), n_flows=1)
    lm = summarize_result(lres)[0]
    bm = summarize_result(bres)[0]
    lc = leo_box["cca"]
    bc = bbr_box["cca"]
    n = max(1, lc.diag_acks)
    nr = max(1, lc.diag_n_rate)
    bn = max(1, bc.diag_n)
    row = {
        "seed": seed,
        "fillgap_gp": lm.goodput_bps / 1e6,
        "bbr_gp": bm.goodput_bps / 1e6,
        "delta_gp": (lm.goodput_bps - bm.goodput_bps) / 1e6,
        "fillgap_p95": lm.p95_rtt_s * 1000,
        "bbr_p95": bm.p95_rtt_s * 1000,
        "delay_clean_frac": lc.diag_delay_clean / n,
        "delivery_caught_frac": lc.diag_delivery_caught / n,
        "below_085_frac": lc.diag_below_085 / n,
        "leftover_band_frac": lc.diag_in_leftover_band / n,
        "softceil_eligible_frac": lc.diag_softceil_eligible / n,
        "at_or_above_090_frac": lc.diag_at_or_above_090 / n,
        "mean_cwnd_fillgap": lc.diag_cwnd_sum / nr,
        "mean_cwnd_bbr": bc.diag_cwnd_sum / bn,
        "mean_del_bdp": lc.diag_del_bdp_sum / nr,
        "cwnd_over_del_bdp": (lc.diag_cwnd_sum / nr) / max(1.0, lc.diag_del_bdp_sum / nr),
        "mean_delivery_mbps": lc.diag_del_sum / nr / 1e6,
        "mean_bw_est_mbps": lc.diag_bw_sum / nr / 1e6,
        "fillgap_fills": lc.fillgap_fills,
        "lsg_clamps": lc.lsg_clamps,
        "reconfigs": lc.reconfigs_detected,
        "mean_inflight_fillgap": _mean(lres.flows[0].inflight),
        "mean_inflight_bbr": _mean(bres.flows[0].inflight),
    }
    return row


def main() -> None:
    assert PRODUCT_PATH_PROFILE == "starlink_v1"
    assert SOFT_QIR_ALPHA == 0.20
    OUT.mkdir(parents=True, exist_ok=True)
    rows = []
    print(
        f"diag v3.18 SoftCeil starlink_v1 seeds={PRODUCT_SEEDS} α={SOFT_QIR_ALPHA}",
        flush=True,
    )
    for seed in PRODUCT_SEEDS:
        print(f"seed {seed} ...", flush=True)
        row = run_seed(seed)
        rows.append(row)
        print(
            f"  FG {row['fillgap_gp']:.2f} vs BBR {row['bbr_gp']:.2f} "
            f"Δ={row['delta_gp']:+.2f}  softceil_elig={row['softceil_eligible_frac']:.3f} "
            f"cwnd/delBDP={row['cwnd_over_del_bdp']:.2f} "
            f"band={row['leftover_band_frac']:.3f}",
            flush=True,
        )

    means = {k: _mean([r[k] for r in rows]) for k in rows[0] if k != "seed"}
    by_seed = {r["seed"]: r for r in rows}
    s13 = by_seed[13]
    others = [r for r in rows if r["seed"] in (7, 99, 123)]
    s13_needs = s13["softceil_eligible_frac"] >= 0.02 and s13["delta_gp"] < -0.20
    others_need = any(
        r["softceil_eligible_frac"] >= 0.05 and r["delta_gp"] < -0.15 for r in others
    )
    hypothesis = (
        "CONFIRMED"
        if s13_needs
        else ("PARTIAL" if s13["softceil_eligible_frac"] >= 0.02 else "DISCARDED")
    )
    payload = {
        "era": "starlink_v1",
        "synthetic": True,
        "soft_qir_alpha": SOFT_QIR_ALPHA,
        "seeds": list(PRODUCT_SEEDS),
        "fillgap_on": True,
        "openslot_on": True,
        "soft_ceil_on": False,
        "fill_gap_ceiling_untouched": 0.85,
        "openslot_threshold_untouched": 0.80,
        "per_seed": rows,
        "means": means,
        "floors": {
            "fillgap_seed13_gp": FILLGAP_SEED13_GP,
            "fillgap_gp_lock": FILLGAP_GP_LOCK,
        },
        "hypotheses": {
            "H1_seed13_sits_in_085_090_band": (
                "After FillGap, seed 13 leftover is cwnd sitting in the "
                "0.85-0.90 delivery-BDP band on delay-clean, delivery-caught ACKs."
            ),
            "H2_winners_do_not_need_softceil": (
                "Seeds 7/99/123 already beat BBR; SoftCeil eligible frac "
                "should be small or they are not the leftover."
            ),
        },
        "verdicts": {
            "H1": hypothesis,
            "H2": "CONFIRMED" if not others_need else "DISCARDED",
            "seed13_needs_softceil": s13_needs,
            "winners_need_softceil": others_need,
        },
    }
    (OUT / "diagnosis.json").write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print("\n=== means ===")
    for k, v in means.items():
        print(f"  {k:32s} {v:.4f}")
    print(f"\nH1 SoftCeil leftover: {hypothesis}")
    print(f"H2 7/99/123 do not need it: {payload['verdicts']['H2']}")
    print(f"wrote {OUT / 'diagnosis.json'}")


if __name__ == "__main__":
    main()
