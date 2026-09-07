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


# v3.20 detect over-fire. Same leftover window as post-path-HO ACK split.
NEAR_HO_WINDOW_S = 1.4

# Endpoint-legal shadow gates. None of these drop ep:loss_burst.
SHADOW_GATE_NAMES = ("score_ge_1_85", "score_ge_2_0", "multi_reason", "rtt_anchor")


def _event_reasons(ev: dict) -> list[str]:
    raw = ev.get("reasons")
    if isinstance(raw, list) and raw:
        return [str(x) for x in raw if x]
    reason = str(ev.get("reason") or "")
    return [r for r in reason.split("+") if r]


def _shadow_pass(name: str, ev: dict) -> bool:
    reasons = _event_reasons(ev)
    # Integrity: never drop ep:loss_burst, even in a shadow scorecard.
    if "loss_burst" in reasons:
        return True
    score = float(ev.get("score") or 0.0)
    n = int(ev.get("n_reasons") or len(set(reasons)))
    if name == "score_ge_1_85":
        return score >= 1.85
    if name == "score_ge_2_0":
        return score >= 2.0
    if name == "multi_reason":
        return n >= 2
    if name == "rtt_anchor":
        return any(r.startswith("rtt_") for r in reasons)
    return True


def nearest_path_ho_dt(t: float, handovers: list[float]) -> float | None:
    if not handovers:
        return None
    return min(abs(float(t) - float(h)) for h in handovers)


def classify_detect_overfire(
    events: list[dict],
    handovers: list[float],
    window_s: float = NEAR_HO_WINDOW_S,
) -> dict:
    """Post-hoc detect vs real path HO. Observe only; never a send lever.

    Near = |t − HO| ≤ window. Shadow gates are endpoint-legal and must not
    drop loss_burst. A gate is reckless if it cuts a path HO the current
    detector already covered.
    """
    hos = [float(h) for h in handovers]
    classified = []
    reason_counts: dict[str, int] = {}
    source_counts: dict[str, int] = {}
    near_n = 0
    far_n = 0
    for ev in events:
        t = float(ev.get("t") or 0.0)
        dt = nearest_path_ho_dt(t, hos)
        near = dt is not None and dt <= window_s
        reasons = _event_reasons(ev)
        source = str(ev.get("source") or ("on_loss" if reasons == ["loss_burst"] else "fusion"))
        row = {
            "t": t,
            "reason": ev.get("reason"),
            "score": _json_num(float(ev.get("score") or 0.0)),
            "source": source,
            "n_reasons": int(ev.get("n_reasons") or len(set(reasons))),
            "primary": ev.get("primary") or (reasons[0] if reasons else ""),
            "reasons": reasons,
            "nearest_path_ho_dt": _json_num(dt),
            "near_path_ho": bool(near),
        }
        classified.append(row)
        if near:
            near_n += 1
        else:
            far_n += 1
        for r in set(reasons):
            reason_counts[r] = reason_counts.get(r, 0) + 1
        source_counts[source] = source_counts.get(source, 0) + 1

    ho_covered = 0
    for h in hos:
        if any(
            ev.get("nearest_path_ho_dt") is not None
            and ev["nearest_path_ho_dt"] <= window_s
            and abs(float(ev["t"]) - h) <= window_s
            for ev in classified
        ):
            ho_covered += 1
    ho_recall = _frac(float(ho_covered), float(len(hos))) if hos else None

    shadows = {}
    for name in SHADOW_GATE_NAMES:
        kept = [ev for ev in classified if _shadow_pass(name, ev)]
        far_cut = sum(1 for ev in classified if not ev["near_path_ho"] and not _shadow_pass(name, ev))
        near_cut = sum(1 for ev in classified if ev["near_path_ho"] and not _shadow_pass(name, ev))
        covered = 0
        for h in hos:
            if any(abs(float(ev["t"]) - h) <= window_s for ev in kept):
                covered += 1
        recall = _frac(float(covered), float(len(hos))) if hos else None
        far_cut_frac = _frac(float(far_cut), float(far_n)) if far_n else None
        ho_recall_ok = recall is not None and ho_recall is not None and recall + 1e-12 >= ho_recall
        cuts_far = bool(far_cut_frac is not None and far_cut_frac >= 0.50)
        shadows[name] = {
            "kept": len(kept),
            "near_cut": near_cut,
            "far_cut": far_cut,
            "far_cut_frac": far_cut_frac,
            "ho_covered": covered,
            "ho_recall": recall,
            "keeps_current_ho_recall": ho_recall_ok,
            "cuts_half_far": cuts_far,
            "reckless": bool(hos and not ho_recall_ok),
            "promising": bool(ho_recall_ok and cuts_far),
        }

    promising = [n for n, g in shadows.items() if g["promising"]]
    reckless_any = any(g["reckless"] and g["far_cut"] > 0 for g in shadows.values())
    if promising:
        h5 = "PROMISING"
    elif reckless_any:
        h5 = "RECKLESS"
    else:
        h5 = "WEAK"
    primary_far = {}
    for ev in classified:
        if ev["near_path_ho"]:
            continue
        p = str(ev.get("primary") or "")
        if p:
            primary_far[p] = primary_far.get(p, 0) + 1
    top_far = max(primary_far, key=primary_far.get) if primary_far else ""
    loss_burst_far = reason_counts.get("loss_burst", 0)
    # H6: a single primary reason owns ≥ half of far fires.
    top_far_n = primary_far.get(top_far, 0) if top_far else 0
    h6 = bool(far_n and top_far_n >= 0.50 * far_n)

    return {
        "window_s": window_s,
        "n_events": len(classified),
        "n_path_ho": len(hos),
        "near_n": near_n,
        "far_n": far_n,
        "detect_over_path_ho": _frac(float(len(classified)), float(len(hos))) if hos else None,
        "far_frac": _frac(float(far_n), float(len(classified))) if classified else None,
        "ho_covered": ho_covered,
        "ho_recall": ho_recall,
        "reason_counts": reason_counts,
        "source_counts": source_counts,
        "far_primary_counts": primary_far,
        "shadow_gates": shadows,
        "promising_gates": promising,
        "h5_tighter_gate": h5,
        "h6_single_far_reason": h6,
        "h6_top_far_primary": top_far,
        "events": classified,
        "note": (
            "Shadow gates are observe-only. None drop ep:loss_burst. "
            "Path HO is never a live detect input. Do not bump Current."
        ),
        "loss_burst_mentions": loss_burst_far,
    }


def detect_overfire_hook(
    *,
    leo_snaps: list[dict],
    handovers_by_seed: dict[int, list[float]] | None = None,
    leo_gp: float | None = None,
    leo_p95: float | None = None,
    bbr_gp: float | None = None,
    bbr_p95: float | None = None,
) -> dict:
    """Official leftover follow-on: detect over-fire vs dual-gate bars."""
    bars = dual_gate_bars()
    per_seed = []
    all_far_frac = []
    all_over = []
    all_recall = []
    shadow_votes: dict[str, list[bool]] = {n: [] for n in SHADOW_GATE_NAMES}
    h5_votes: list[str] = []
    h6_votes: list[bool] = []
    reason_sum: dict[str, int] = {}
    source_sum: dict[str, int] = {}
    for snap in leo_snaps:
        if not snap:
            continue
        seed = snap.get("seed")
        hos = []
        if handovers_by_seed is not None and seed in handovers_by_seed:
            hos = list(handovers_by_seed[seed])
        elif snap.get("handovers"):
            hos = list(snap.get("handovers") or [])
        events = list(snap.get("obs_detect_events") or [])
        clf = classify_detect_overfire(events, hos)
        for r, n in clf["reason_counts"].items():
            reason_sum[r] = reason_sum.get(r, 0) + int(n)
        for r, n in clf.get("source_counts", {}).items():
            source_sum[r] = source_sum.get(r, 0) + int(n)
        if clf["far_frac"] is not None:
            all_far_frac.append(clf["far_frac"])
        if clf["detect_over_path_ho"] is not None:
            all_over.append(clf["detect_over_path_ho"])
        if clf["ho_recall"] is not None:
            all_recall.append(clf["ho_recall"])
        h5_votes.append(clf["h5_tighter_gate"])
        h6_votes.append(bool(clf["h6_single_far_reason"]))
        for name, g in clf["shadow_gates"].items():
            shadow_votes[name].append(bool(g["promising"]))
        per_seed.append(
            {
                "seed": seed,
                "path_handovers": clf["n_path_ho"],
                "detects": clf["n_events"],
                "near_n": clf["near_n"],
                "far_n": clf["far_n"],
                "far_frac": clf["far_frac"],
                "detect_over_path_ho": clf["detect_over_path_ho"],
                "ho_recall": clf["ho_recall"],
                "reason_counts": clf["reason_counts"],
                "source_counts": clf.get("source_counts"),
                "far_primary_counts": clf["far_primary_counts"],
                "h5_tighter_gate": clf["h5_tighter_gate"],
                "promising_gates": clf["promising_gates"],
                "shadow_gates": clf["shadow_gates"],
            }
        )
    far_mean = sum(all_far_frac) / len(all_far_frac) if all_far_frac else None
    over_mean = sum(all_over) / len(all_over) if all_over else None
    recall_mean = sum(all_recall) / len(all_recall) if all_recall else None
    promising_any = [n for n, votes in shadow_votes.items() if votes and all(votes)]
    # H4: most detects sit far from a real path HO.
    h4 = bool(far_mean is not None and far_mean >= 0.60)
    if promising_any:
        h5 = "PROMISING"
    elif h5_votes and any(v == "RECKLESS" for v in h5_votes) and not all(
        v == "WEAK" for v in h5_votes
    ):
        h5 = "RECKLESS" if all(v == "RECKLESS" for v in h5_votes) else "MIXED"
    else:
        h5 = "WEAK"
    h6 = bool(h6_votes) and all(h6_votes)
    abs_gp_ok = leo_gp is not None and leo_gp >= bars["gp_mean"]
    abs_p95_ok = leo_p95 is not None and leo_p95 <= bars["p95_mean"]
    beats_fillgap = (
        leo_gp is not None
        and leo_p95 is not None
        and leo_gp > bars["fillgap_gp_lock"]
        and leo_p95 <= bars["fillgap_p95_lock"]
    )
    on_loss_n = source_sum.get("on_loss", 0)
    fusion_n = source_sum.get("fusion", 0)
    if h5 == "PROMISING":
        rec = (
            f"Shadow gate(s) {promising_any} keep current HO recall and cut "
            "≥ half of far fires. Next cook may try that as an opt-in "
            "endpoint lever (default False). Do not gate ep:loss_burst. "
            "Do not retry a cruise-band fill."
        )
    elif h5 == "RECKLESS":
        rec = (
            "A legal shadow tighter gate that cuts far fires also drops a "
            "path HO the current detector already covered. Observe-only: "
            "do not cook a score/multi/RTT-anchor fill. Do not gate "
            "ep:loss_burst. Do not retune detect cooldown."
        )
    else:
        rec = (
            "Legal shadow gates (score 1.85/2.0, multi-reason, RTT-anchor) "
            f"do not cut the over-fire. on_loss loss_burst is {on_loss_n} "
            f"events vs fusion {fusion_n}; far fires are loss_burst, and "
            "ep:loss_burst stays ungated. Fusion already sits on real path "
            "HOs. Observe-only: do not cook a fusion-threshold raise, do "
            "not retry SoftCeil, do not bump Current. Next cook, if any, "
            "needs a new mobility-loss taxonomy — or leave detect alone."
        )
    return {
        "era": "starlink_v1",
        "synthetic": True,
        "current_paid": False,
        "current_stays": "v3.17 FillGap",
        "softceil_decision": "REJECT",
        "lever": "none (observe + shadow gates)",
        "bars": bars,
        "window_s": NEAR_HO_WINDOW_S,
        "means": {
            "detect_over_path_ho": _json_num(over_mean),
            "far_frac": _json_num(far_mean),
            "ho_recall": _json_num(recall_mean),
        },
        "reason_counts_sum": reason_sum,
        "source_counts_sum": source_sum,
        "promising_gates": promising_any,
        "per_seed": per_seed,
        "hypotheses": {
            "H4_most_detects_far_from_path_ho": h4,
            "H5_tighter_gate_keeps_ho_cuts_far": h5,
            "H6_one_primary_owns_half_far": h6,
            "note": (
                "Follow-on to leftover H2 (detect over-fire CONFIRMED). "
                "Shadow only. Never gates ep:loss_burst. Not a cook."
            ),
        },
        "gates": {
            "gp_ge_75": abs_gp_ok,
            "p95_le_138_8": abs_p95_ok,
            "beats_fillgap_lock": beats_fillgap,
            "bump_current": False,
        },
        "measured_gp": leo_gp,
        "measured_p95": leo_p95,
        "bbr_gp": bbr_gp,
        "bbr_p95": bbr_p95,
        "recommendation": rec,
    }


# v3.21 on_loss / ep:loss_burst taxonomy. These shadows MAY classify
# loss_burst - that is the leftover v3.20 named. Fusion stays kept.
# Path HO is still never a live detect input.
PACEMAKER_GAP_LO_S = 1.4
PACEMAKER_GAP_HI_S = 1.8
TAXONOMY_GATE_NAMES = (
    "cluster_ge_3",
    "cluster_ge_4",
    "first_after_3s",
    "first_after_5s",
    "rtt_ge_1_12",
)


def _taxonomy_pass(name: str, ev: dict) -> bool:
    """Endpoint-legal taxonomy. Fusion always kept. May drop loss_burst."""
    source = str(ev.get("source") or "")
    reasons = _event_reasons(ev)
    if source == "fusion" or (reasons and "loss_burst" not in reasons):
        return True
    cluster_n = int(ev.get("cluster_n") or 0)
    dt_last = ev.get("dt_last_detect")
    rtt_ratio = ev.get("rtt_ratio")
    if name == "cluster_ge_3":
        return cluster_n >= 3
    if name == "cluster_ge_4":
        return cluster_n >= 4
    if name == "first_after_3s":
        return dt_last is not None and float(dt_last) >= 3.0
    if name == "first_after_5s":
        return dt_last is not None and float(dt_last) >= 5.0
    if name == "rtt_ge_1_12":
        return rtt_ratio is not None and float(rtt_ratio) >= 1.12
    return True


def classify_loss_taxonomy(
    events: list[dict],
    handovers: list[float],
    window_s: float = NEAR_HO_WINDOW_S,
) -> dict:
    """When is on_loss a hop vs cruise flicker? Observe only.

    Taxonomy shadows may drop ep:loss_burst. A gate is reckless if it
    drops a path HO the current detector already covered.
    """
    base = classify_detect_overfire(events, handovers, window_s=window_s)
    classified = base["events"]
    # classify_detect_overfire keeps event order — zip taxonomy fields back on.
    for row, raw in zip(classified, events):
        row["cluster_n"] = int(raw.get("cluster_n") or 0)
        row["rtt_ratio"] = (
            _json_num(raw.get("rtt_ratio")) if raw.get("rtt_ratio") is not None else None
        )
        row["dt_last_detect"] = (
            _json_num(raw.get("dt_last_detect"))
            if raw.get("dt_last_detect") is not None
            else None
        )
        row["in_reprobe"] = bool(raw.get("in_reprobe"))
        row["region"] = raw.get("region")
        row["source"] = str(raw.get("source") or row.get("source") or "")

    hos = [float(h) for h in handovers]
    on_loss_only_ho = 0
    fusion_covered_ho = 0
    for h in hos:
        near = [ev for ev in classified if abs(float(ev["t"]) - h) <= window_s]
        if not near:
            continue
        if any(ev.get("source") == "fusion" for ev in near):
            fusion_covered_ho += 1
        elif all(ev.get("source") == "on_loss" for ev in near):
            on_loss_only_ho += 1

    far_on_loss = [
        ev
        for ev in classified
        if not ev.get("near_path_ho") and ev.get("source") == "on_loss"
    ]
    far_cluster2 = sum(1 for ev in far_on_loss if int(ev.get("cluster_n") or 0) == 2)
    far_pace = sum(
        1
        for ev in far_on_loss
        if ev.get("dt_last_detect") is not None
        and PACEMAKER_GAP_LO_S - 1e-9 <= float(ev["dt_last_detect"]) <= PACEMAKER_GAP_HI_S
    )
    near_on_loss = [
        ev
        for ev in classified
        if ev.get("near_path_ho") and ev.get("source") == "on_loss"
    ]
    near_cluster2 = sum(1 for ev in near_on_loss if int(ev.get("cluster_n") or 0) == 2)

    shadows = {}
    ho_recall = base["ho_recall"]
    far_n = base["far_n"]
    for name in TAXONOMY_GATE_NAMES:
        kept = [ev for ev in classified if _taxonomy_pass(name, ev)]
        far_cut = sum(
            1 for ev in classified if not ev["near_path_ho"] and not _taxonomy_pass(name, ev)
        )
        near_cut = sum(
            1 for ev in classified if ev["near_path_ho"] and not _taxonomy_pass(name, ev)
        )
        covered = 0
        for h in hos:
            if any(abs(float(ev["t"]) - h) <= window_s for ev in kept):
                covered += 1
        recall = _frac(float(covered), float(len(hos))) if hos else None
        far_cut_frac = _frac(float(far_cut), float(far_n)) if far_n else None
        ho_recall_ok = recall is not None and ho_recall is not None and recall + 1e-12 >= ho_recall
        cuts_far = bool(far_cut_frac is not None and far_cut_frac >= 0.50)
        shadows[name] = {
            "kept": len(kept),
            "near_cut": near_cut,
            "far_cut": far_cut,
            "far_cut_frac": far_cut_frac,
            "ho_covered": covered,
            "ho_recall": recall,
            "keeps_current_ho_recall": ho_recall_ok,
            "cuts_half_far": cuts_far,
            "reckless": bool(hos and not ho_recall_ok),
            "promising": bool(ho_recall_ok and cuts_far),
        }

    promising = [n for n, g in shadows.items() if g["promising"]]
    reckless_any = any(g["reckless"] and g["far_cut"] > 0 for g in shadows.values())
    if promising:
        h8 = "PROMISING"
    elif reckless_any:
        h8 = "RECKLESS"
    else:
        h8 = "WEAK"

    # H7: leftover far on_loss is the 1.4s pacemaker / cluster-2 cruise.
    h7 = bool(
        far_on_loss
        and (
            far_cluster2 >= 0.60 * len(far_on_loss)
            or far_pace >= 0.60 * len(far_on_loss)
        )
    )
    # H9: some path HOs are covered only by on_loss (fusion miss).
    h9 = bool(on_loss_only_ho > 0)

    return {
        **base,
        "on_loss_only_ho": on_loss_only_ho,
        "fusion_covered_ho": fusion_covered_ho,
        "far_on_loss_n": len(far_on_loss),
        "far_cluster2_n": far_cluster2,
        "far_pacemaker_n": far_pace,
        "near_on_loss_n": len(near_on_loss),
        "near_cluster2_n": near_cluster2,
        "taxonomy_gates": shadows,
        "promising_taxonomy": promising,
        "h7_far_is_pacemaker": h7,
        "h8_taxonomy_keeps_ho_cuts_far": h8,
        "h9_some_ho_on_loss_only": h9,
        "taxonomy_note": (
            "Taxonomy shadows may drop ep:loss_burst. Path HO is never a "
            "live detect input. Do not bump Current."
        ),
    }


def loss_taxonomy_hook(
    *,
    leo_snaps: list[dict],
    handovers_by_seed: dict[int, list[float]] | None = None,
    leo_gp: float | None = None,
    leo_p95: float | None = None,
    bbr_gp: float | None = None,
    bbr_p95: float | None = None,
) -> dict:
    """Official leftover follow-on: on_loss / ep:loss_burst taxonomy."""
    bars = dual_gate_bars()
    per_seed = []
    h7_votes: list[bool] = []
    h8_votes: list[str] = []
    h9_votes: list[bool] = []
    shadow_votes: dict[str, list[bool]] = {n: [] for n in TAXONOMY_GATE_NAMES}
    far_cluster2 = 0
    far_pace = 0
    far_on_loss = 0
    on_loss_only_ho = 0
    fusion_covered_ho = 0
    suppressed = 0
    all_far_frac = []
    all_over = []
    all_recall = []
    for snap in leo_snaps:
        if not snap:
            continue
        seed = snap.get("seed")
        hos = []
        if handovers_by_seed is not None and seed in handovers_by_seed:
            hos = list(handovers_by_seed[seed])
        elif snap.get("handovers"):
            hos = list(snap.get("handovers") or [])
        events = list(snap.get("obs_detect_events") or [])
        clf = classify_loss_taxonomy(events, hos)
        h7_votes.append(bool(clf["h7_far_is_pacemaker"]))
        h8_votes.append(str(clf["h8_taxonomy_keeps_ho_cuts_far"]))
        h9_votes.append(bool(clf["h9_some_ho_on_loss_only"]))
        for name, g in clf["taxonomy_gates"].items():
            shadow_votes[name].append(bool(g["promising"]))
        far_cluster2 += int(clf["far_cluster2_n"])
        far_pace += int(clf["far_pacemaker_n"])
        far_on_loss += int(clf["far_on_loss_n"])
        on_loss_only_ho += int(clf["on_loss_only_ho"])
        fusion_covered_ho += int(clf["fusion_covered_ho"])
        suppressed += int(snap.get("obs_loss_suppressed") or 0)
        if clf["far_frac"] is not None:
            all_far_frac.append(clf["far_frac"])
        if clf["detect_over_path_ho"] is not None:
            all_over.append(clf["detect_over_path_ho"])
        if clf["ho_recall"] is not None:
            all_recall.append(clf["ho_recall"])
        per_seed.append(
            {
                "seed": seed,
                "path_handovers": clf["n_path_ho"],
                "detects": clf["n_events"],
                "near_n": clf["near_n"],
                "far_n": clf["far_n"],
                "far_frac": clf["far_frac"],
                "ho_recall": clf["ho_recall"],
                "on_loss_only_ho": clf["on_loss_only_ho"],
                "fusion_covered_ho": clf["fusion_covered_ho"],
                "far_on_loss_n": clf["far_on_loss_n"],
                "far_cluster2_n": clf["far_cluster2_n"],
                "far_pacemaker_n": clf["far_pacemaker_n"],
                "near_on_loss_n": clf["near_on_loss_n"],
                "near_cluster2_n": clf["near_cluster2_n"],
                "obs_loss_suppressed": int(snap.get("obs_loss_suppressed") or 0),
                "h7_far_is_pacemaker": clf["h7_far_is_pacemaker"],
                "h8_taxonomy_keeps_ho_cuts_far": clf["h8_taxonomy_keeps_ho_cuts_far"],
                "h9_some_ho_on_loss_only": clf["h9_some_ho_on_loss_only"],
                "promising_taxonomy": clf["promising_taxonomy"],
                "taxonomy_gates": clf["taxonomy_gates"],
                "source_counts": clf.get("source_counts"),
            }
        )
    promising_any = [n for n, votes in shadow_votes.items() if votes and all(votes)]
    h7 = bool(h7_votes) and all(h7_votes)
    h9 = bool(h9_votes) and all(h9_votes)
    if promising_any:
        h8 = "PROMISING"
    elif h8_votes and any(v == "RECKLESS" for v in h8_votes):
        h8 = "RECKLESS" if all(v == "RECKLESS" for v in h8_votes) else "MIXED"
    else:
        h8 = "WEAK"
    abs_gp_ok = leo_gp is not None and leo_gp >= bars["gp_mean"]
    abs_p95_ok = leo_p95 is not None and leo_p95 <= bars["p95_mean"]
    beats_fillgap = (
        leo_gp is not None
        and leo_p95 is not None
        and leo_gp > bars["fillgap_gp_lock"]
        and leo_p95 <= bars["fillgap_p95_lock"]
    )
    if h8 == "PROMISING":
        rec = (
            f"Taxonomy gate(s) {promising_any} keep current HO recall and "
            "cut ≥ half of far on_loss fires. Next cook may try that as an "
            "opt-in endpoint lever (default False). Do not retry SoftCeil. "
            "Do not bump Current without a 5-seed table that beats FillGap."
        )
    elif h9:
        rec = (
            "Far on_loss is the 1.4s pacemaker, but some path HOs are "
            "covered only by on_loss (fusion miss). Legal taxonomy shadows "
            "that cut the leftover also drop those hops. REJECT a live "
            "loss-burst gate. Leave detect alone. Do not bump Current."
        )
    else:
        rec = (
            "No legal on_loss taxonomy keeps HO recall and cuts ≥ half of "
            "far fires. Stay observe-only. Do not gate ep:loss_burst. Do "
            "not retry SoftCeil. Do not bump Current."
        )
    return {
        "era": "starlink_v1",
        "synthetic": True,
        "current_paid": False,
        "current_stays": "v3.17 FillGap",
        "softceil_decision": "REJECT",
        "lever": "none (observe + taxonomy shadows)",
        "bars": bars,
        "window_s": NEAR_HO_WINDOW_S,
        "means": {
            "detect_over_path_ho": _json_num(sum(all_over) / len(all_over) if all_over else None),
            "far_frac": _json_num(sum(all_far_frac) / len(all_far_frac) if all_far_frac else None),
            "ho_recall": _json_num(sum(all_recall) / len(all_recall) if all_recall else None),
        },
        "far_on_loss_n": far_on_loss,
        "far_cluster2_n": far_cluster2,
        "far_pacemaker_n": far_pace,
        "on_loss_only_ho": on_loss_only_ho,
        "fusion_covered_ho": fusion_covered_ho,
        "obs_loss_suppressed": suppressed,
        "promising_taxonomy": promising_any,
        "per_seed": per_seed,
        "hypotheses": {
            "H7_far_on_loss_is_pacemaker": h7,
            "H8_taxonomy_keeps_ho_cuts_far": h8,
            "H9_some_ho_on_loss_only": h9,
            "note": (
                "Follow-on to v3.20 leftover (fusion clean; on_loss leftover). "
                "Taxonomy shadows may classify loss_burst. Not a cook. "
                "Do not bump Current."
            ),
        },
        "gates": {
            "gp_ge_75": abs_gp_ok,
            "p95_le_138_8": abs_p95_ok,
            "beats_fillgap_lock": beats_fillgap,
            "bump_current": False,
        },
        "measured_gp": leo_gp,
        "measured_p95": leo_p95,
        "bbr_gp": bbr_gp,
        "bbr_p95": bbr_p95,
        "recommendation": rec,
    }
