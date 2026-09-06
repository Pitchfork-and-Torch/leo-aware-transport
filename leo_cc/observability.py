"""Starlink leftover observability hooks (research; not Current).

SoftCeil REJECT showed the leftover after FillGap is not the 0.85-0.90
cruise band. These helpers turn always-on CCA leftover counters into a
scorecard section so the next cook measures cruise vs post-detect vs
REPROBE instead of writing another one-off diag.

Never marks paid / Current. Dual-gate bars stay 75 / 138.8.
"""
from __future__ import annotations

from leo_cc.harness import PRODUCT_GP_BAR, PRODUCT_P95_BAR, PRODUCT_TERR_GP_BAR

# Cited Current lock (FillGap). Observability must not redefine these.
FILLGAP_GP_LOCK = 82.45
FILLGAP_P95_LOCK = 76.26
BBR_GP_LOCK = 82.44
BBR_P95_LOCK = 76.66
SOFTCEIL_GP_REJECT = 82.35

SNAPSHOT_FRAC_KEYS = (
    "delay_clean_frac",
    "delivery_caught_frac",
    "below_085_frac",
    "leftover_band_frac",
    "at_or_above_090_frac",
    "softceil_eligible_frac",
    "fillgap_eligible_frac",
    "reprobe_ack_frac",
    "post_detect_ack_frac",
    "cruise_ack_frac",
    "post_path_ho_ack_frac",
    "below_085_reprobe_frac",
    "below_085_post_detect_frac",
    "below_085_cruise_frac",
    "leftover_band_reprobe_frac",
    "leftover_band_post_detect_frac",
    "leftover_band_cruise_frac",
    "below_085_post_path_ho_frac",
    "leftover_band_post_path_ho_frac",
)


def dual_gate_bars() -> dict:
    """Frozen product dual-gate bars. Do not quietly retune."""
    return {
        "gp_mean": PRODUCT_GP_BAR,
        "p95_mean": PRODUCT_P95_BAR,
        "terr_gp": PRODUCT_TERR_GP_BAR,
        "fillgap_gp_lock": FILLGAP_GP_LOCK,
        "fillgap_p95_lock": FILLGAP_P95_LOCK,
        "bbr_gp_lock": BBR_GP_LOCK,
        "bbr_p95_lock": BBR_P95_LOCK,
        "softceil_gp_reject": SOFTCEIL_GP_REJECT,
    }


def _frac(num: float, den: float) -> float | None:
    if den <= 0:
        return None
    return num / den


def _json_num(v: float | None) -> float | None:
    if v is None:
        return None
    if v != v:  # NaN
        return None
    return float(v)


def leftover_fractions(snap: dict | None) -> dict:
    """Normalize leftover snapshot fractions. Missing snap → empty dict."""
    if not snap:
        return {}
    out = {k: _json_num(float(snap[k])) for k in SNAPSHOT_FRAC_KEYS if k in snap}
    n_ho = float(snap.get("obs_path_handovers") or 0.0)
    detects = float(snap.get("reconfigs_detected") or 0.0)
    out["detect_over_path_ho"] = _frac(detects, n_ho)
    return out


def leftover_scorecard_hook(
    *,
    leo_snaps: list[dict],
    handovers: list[float] | None = None,
    leo_gp: float | None = None,
    leo_p95: float | None = None,
    bbr_gp: float | None = None,
    bbr_p95: float | None = None,
) -> dict:
    """Build a leftover observability section. Never Current / paid."""
    bars = dual_gate_bars()
    fracs = [leftover_fractions(s) for s in leo_snaps if s]
    means = {}
    if fracs:
        keys = set().union(*[f.keys() for f in fracs])
        for k in sorted(keys):
            xs = [f[k] for f in fracs if k in f and f[k] is not None]
            means[k] = _json_num(sum(xs) / len(xs)) if xs else None
    n_ho = 0
    if handovers:
        n_ho = len(handovers)
    elif leo_snaps:
        n_ho = int(sum(int(s.get("obs_path_handovers") or 0) for s in leo_snaps) / max(1, len(leo_snaps)))
    detects = 0.0
    if leo_snaps:
        detects = sum(float(s.get("reconfigs_detected") or 0) for s in leo_snaps) / max(
            1, len(leo_snaps)
        )
    cruise_band = means.get("leftover_band_cruise_frac", float("nan"))
    post_band = means.get("leftover_band_post_detect_frac", float("nan"))
    cruise_below = means.get("below_085_cruise_frac", float("nan"))
    post_below = means.get("below_085_post_detect_frac", float("nan"))
    leftover_is_post_detect = (
        post_band is not None
        and cruise_band is not None
        and (
            post_band > cruise_band
            or (
                post_below is not None
                and cruise_below is not None
                and post_below > cruise_below
            )
        )
    )
    ho_ack = means.get("post_path_ho_ack_frac")
    ho_band = means.get("leftover_band_post_path_ho_frac")
    ho_below = means.get("below_085_post_path_ho_frac")
    leftover_band = means.get("leftover_band_frac")
    below_all = means.get("below_085_frac")
    leftover_is_real_ho = bool(
        ho_ack
        and leftover_band
        and ho_band is not None
        and leftover_band > 0
        and (ho_band / leftover_band) > (1.5 * ho_ack)
    )
    below_is_real_ho = bool(
        ho_ack
        and below_all
        and ho_below is not None
        and below_all > 0
        and (ho_below / below_all) > (1.5 * ho_ack)
    )
    return {
        "era": "starlink_v1",
        "synthetic": True,
        "current_paid": False,
        "current_stays": "v3.17 FillGap",
        "softceil_decision": "REJECT",
        "bars": bars,
        "path_handovers_mean": n_ho,
        "reconfigs_detected_mean": detects,
        "detect_over_path_ho": _frac(detects, float(n_ho)) if n_ho else float("nan"),
        "means": means,
        "per_seed": [
            {
                "reconfigs_detected": s.get("reconfigs_detected"),
                "obs_path_handovers": s.get("obs_path_handovers"),
                "lsg_clamps": s.get("lsg_clamps"),
                "lsg_clamps_post_detect": s.get("lsg_clamps_post_detect"),
                "lsg_clamps_cruise": s.get("lsg_clamps_cruise"),
                "leftover_band_frac": s.get("leftover_band_frac"),
                "leftover_band_cruise_frac": s.get("leftover_band_cruise_frac"),
                "leftover_band_post_detect_frac": s.get("leftover_band_post_detect_frac"),
                "leftover_band_post_path_ho_frac": s.get("leftover_band_post_path_ho_frac"),
                "below_085_frac": s.get("below_085_frac"),
                "below_085_cruise_frac": s.get("below_085_cruise_frac"),
                "below_085_post_detect_frac": s.get("below_085_post_detect_frac"),
                "below_085_post_path_ho_frac": s.get("below_085_post_path_ho_frac"),
                "post_path_ho_ack_frac": s.get("post_path_ho_ack_frac"),
                "cwnd_over_del_bdp": s.get("cwnd_over_del_bdp"),
            }
            for s in leo_snaps
            if s
        ],
        "hypotheses": {
            "H1_leftover_is_post_detect_not_cruise_band": leftover_is_post_detect,
            "H2_detect_overfires_vs_path_ho": bool(n_ho and detects > 2.0 * n_ho),
            "H3_leftover_band_concentrated_in_real_ho": leftover_is_real_ho,
            "H3b_below_085_concentrated_in_real_ho": below_is_real_ho,
            "note": (
                "Measured leftover split after SoftCeil REJECT. "
                "Post-detect can be inflated by detect over-fire; "
                "H3 uses real path-HO windows. Not a cook. Do not bump Current."
            ),
        },
        "measured_gp": leo_gp,
        "measured_p95": leo_p95,
        "bbr_gp": bbr_gp,
        "bbr_p95": bbr_p95,
    }
