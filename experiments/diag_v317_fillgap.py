#!/usr/bin/env python3
"""v3.17 diagnosis: seed 13 leftover after OpenSlot is a cwnd gap?

Same rails as the v3.9 lock / v3.16 OpenSlot cook: leo_fast_ho 90s,
seeds 13,7,42,99,123, synthetic starlink_v1, soft-QIR α=0.20, endpoint-only.

Measures OpenSlot (pace leftover already closed) vs BBR: cwnd vs delivery
BDP, delay-clean + delivery-caught underfill, and whether seeds 7/99/123
already sit at/above the FillGap gate.

Does not change CCA defaults.

Usage:
  python3 -m experiments.diag_v317_fillgap
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from leo_cc.ccas import BbrCCA, LeoAwareCCA, MSS
from leo_cc.harness import PRODUCT_PATH_PROFILE, PRODUCT_SEEDS, apply_profile
from leo_cc.metrics import summarize_result
from leo_cc.network import LeoPathConfig
from leo_cc.sim import SOFT_QIR_ALPHA, run_sim

OUT = ROOT / "results" / "archive" / "20260814-v317-fillgap" / "diag"

# OpenSlot leftover floors (official v3.16 archive).
OPENSLOT_SEED13_GP = 96.69
CREST_SEED13_GP = 96.65


class DiagOpenSlot(LeoAwareCCA):
    """Count FillGap-eligible ACKs. No control change."""

    def __init__(self, **kw):
        kw.setdefault("use_openslot", True)
        super().__init__(**kw)
        self.diag_acks = 0
        self.diag_delay_clean = 0
        self.diag_delivery_caught = 0
        self.diag_cwnd_below_del_bdp = 0
        self.diag_fillgap_eligible = 0
        self.diag_inflight_below_del_bdp = 0
        self.diag_cwnd_sum = 0.0
        self.diag_bbr_like_bdp_sum = 0.0
        self.diag_del_bdp_sum = 0.0
        self.diag_del_sum = 0.0
        self.diag_bw_sum = 0.0
        self.diag_n_rate = 0
        self.diag_posthop_eligible = 0
        self.diag_posthop_acks = 0
        self.diag_seed13_clean_under_cwnd = 0

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
        bw_bdp = self.bw_est * rtt_ref / 8.0 if self.bw_est > 0 and rtt_ref > 0 else 0.0
        cwnd_low = del_bdp > 0 and self.cwnd < 0.85 * del_bdp
        inflight_low = del_bdp > 0 and self.bytes_in_flight < 0.85 * del_bdp
        if delay_clean:
            self.diag_delay_clean += 1
        if caught:
            self.diag_delivery_caught += 1
        if cwnd_low:
            self.diag_cwnd_below_del_bdp += 1
        if inflight_low:
            self.diag_inflight_below_del_bdp += 1
        if delay_clean and caught and cwnd_low:
            self.diag_fillgap_eligible += 1
        if delay_clean and caught and inflight_low:
            self.diag_seed13_clean_under_cwnd += 1
        age = t - self.last_reconfig_t
        if age > 0.5:
            self.diag_posthop_acks += 1
            if delay_clean and caught and cwnd_low:
                self.diag_posthop_eligible += 1
        if rate > 0 and self.bw_est > 0:
            self.diag_del_sum += rate
            self.diag_bw_sum += self.bw_est
            self.diag_cwnd_sum += self.cwnd
            self.diag_del_bdp_sum += del_bdp
            self.diag_bbr_like_bdp_sum += bw_bdp
            self.diag_n_rate += 1


class DiagBbr(BbrCCA):
    def __init__(self, **kw):
        super().__init__(**kw)
        self.diag_cwnd_sum = 0.0
        self.diag_bdp_sum = 0.0
        self.diag_n = 0
        self.diag_del_sum = 0.0

    def on_ack(self, t: float, rtt_s: float, bytes_acked: int, lost: int = 0) -> None:
        super().on_ack(t, rtt_s, bytes_acked, lost)
        if self.bw_est > 0 and self.min_rtt < 1e17:
            self.diag_cwnd_sum += self.cwnd
            self.diag_bdp_sum += self._bdp()
            self.diag_n += 1
            if len(self.delivered_marks) >= 2:
                t0, b0 = self.delivered_marks[0]
                t1, b1 = self.delivered_marks[-1]
                dt = t1 - t0
                if dt > 1e-4:
                    self.diag_del_sum += (b1 - b0) * 8.0 / dt


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
        c = DiagOpenSlot()
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
        "openslot_gp": lm.goodput_bps / 1e6,
        "bbr_gp": bm.goodput_bps / 1e6,
        "delta_gp": (lm.goodput_bps - bm.goodput_bps) / 1e6,
        "openslot_p95": lm.p95_rtt_s * 1000,
        "bbr_p95": bm.p95_rtt_s * 1000,
        "delay_clean_frac": lc.diag_delay_clean / n,
        "delivery_caught_frac": lc.diag_delivery_caught / n,
        "cwnd_below_del_bdp_frac": lc.diag_cwnd_below_del_bdp / n,
        "inflight_below_del_bdp_frac": lc.diag_inflight_below_del_bdp / n,
        "fillgap_eligible_frac": lc.diag_fillgap_eligible / n,
        "clean_caught_inflight_low_frac": lc.diag_seed13_clean_under_cwnd / n,
        "posthop_eligible_frac": lc.diag_posthop_eligible / max(1, lc.diag_posthop_acks),
        "mean_cwnd_openslot": lc.diag_cwnd_sum / nr,
        "mean_cwnd_bbr": bc.diag_cwnd_sum / bn,
        "mean_del_bdp": lc.diag_del_bdp_sum / nr,
        "mean_bw_bdp": lc.diag_bbr_like_bdp_sum / nr,
        "mean_bbr_bdp": bc.diag_bdp_sum / bn,
        "cwnd_over_del_bdp": (lc.diag_cwnd_sum / nr) / max(1.0, lc.diag_del_bdp_sum / nr),
        "cwnd_over_bbr_cwnd": (lc.diag_cwnd_sum / nr) / max(1.0, bc.diag_cwnd_sum / bn),
        "mean_delivery_mbps": lc.diag_del_sum / nr / 1e6,
        "mean_bw_est_mbps": lc.diag_bw_sum / nr / 1e6,
        "mean_bbr_delivery_mbps": (bc.diag_del_sum / bn / 1e6) if bn else 0.0,
        "openslot_releases": lc.openslot_releases,
        "lsg_clamps": lc.lsg_clamps,
        "reconfigs": lc.reconfigs_detected,
        "mean_inflight_openslot": _mean(lres.flows[0].inflight),
        "mean_inflight_bbr": _mean(bres.flows[0].inflight),
    }
    return row


def main() -> None:
    assert PRODUCT_PATH_PROFILE == "starlink_v1"
    assert SOFT_QIR_ALPHA == 0.20
    OUT.mkdir(parents=True, exist_ok=True)
    rows = []
    print(
        f"diag v3.17 FillGap starlink_v1 seeds={PRODUCT_SEEDS} α={SOFT_QIR_ALPHA}",
        flush=True,
    )
    for seed in PRODUCT_SEEDS:
        print(f"seed {seed} ...", flush=True)
        row = run_seed(seed)
        rows.append(row)
        print(
            f"  OS {row['openslot_gp']:.2f} vs BBR {row['bbr_gp']:.2f} "
            f"Δ={row['delta_gp']:+.2f}  fillgap_elig={row['fillgap_eligible_frac']:.3f} "
            f"cwnd/delBDP={row['cwnd_over_del_bdp']:.2f} "
            f"cwnd OS/BBR={row['cwnd_over_bbr_cwnd']:.2f}",
            flush=True,
        )

    means = {k: _mean([r[k] for r in rows]) for k in rows[0] if k != "seed"}
    by_seed = {r["seed"]: r for r in rows}
    s13 = by_seed[13]
    others = [r for r in rows if r["seed"] in (7, 99, 123)]
    s13_needs = s13["fillgap_eligible_frac"] >= 0.02 and s13["delta_gp"] < -0.20
    others_need = any(r["fillgap_eligible_frac"] >= 0.05 and r["delta_gp"] < -0.15 for r in others)
    # Hypothesis lives if seed 13 is eligible and 7/99/123 are not the ones that need it.
    hypothesis = "CONFIRMED" if s13_needs and not others_need else (
        "PARTIAL" if s13_needs else "DISCARDED"
    )
    payload = {
        "era": "starlink_v1",
        "synthetic": True,
        "soft_qir_alpha": SOFT_QIR_ALPHA,
        "seeds": list(PRODUCT_SEEDS),
        "openslot_on": True,
        "openslot_threshold_untouched": 0.80,
        "per_seed": rows,
        "means": means,
        "floors": {
            "openslot_seed13_gp": OPENSLOT_SEED13_GP,
            "crest_seed13_gp": CREST_SEED13_GP,
        },
        "hypotheses": {
            "H1_seed13_cwnd_below_delivery_bdp": (
                "After OpenSlot, seed 13 leftover is cwnd sitting below "
                "delivery BDP on delay-clean, delivery-caught ACKs."
            ),
            "H2_winners_do_not_need_fill": (
                "Seeds 7/99/123 already beat BBR; FillGap eligible frac "
                "should be small or they are not cwnd-starved."
            ),
        },
        "verdicts": {
            "H1": hypothesis,
            "H2": "CONFIRMED" if not others_need else "DISCARDED",
            "seed13_needs_fillgap": s13_needs,
            "winners_need_fillgap": others_need,
        },
    }
    (OUT / "diagnosis.json").write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print("\n=== means ===")
    for k, v in means.items():
        print(f"  {k:32s} {v:.4f}")
    print(f"\nH1 FillGap leftover: {hypothesis}")
    print(f"H2 7/99/123 do not need it: {payload['verdicts']['H2']}")
    print(f"wrote {OUT / 'diagnosis.json'}")


if __name__ == "__main__":
    main()
