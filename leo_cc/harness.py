"""Harness eras and product-lock constants.

Two generative eras exist. Never mix them in a Current hero table.

- ope_v36: research / relative-BBR lock (v3.6–v3.7). Absolute 75/138.8 is
  geometrically impossible (Step 0). LeoPathConfig.path_profile default stays
  here so research geometry cannot silently drift.
- starlink_v1: product-lock era (v3.9). Absolute gp≥75 AND p95≤138.8.
  multi_seed / run_suite primary objective default to this profile.

Real Starlink CSV replay is the successor product lock (see
docs/starlink_csv_ingest.md). Coupled-RNG v3.4/v3.5 numbers are a third,
historical physics era.
"""
from __future__ import annotations

from leo_cc.network import LeoPathConfig

# Generative identity (frozen). Do not change without a new research era.
RESEARCH_PATH_PROFILE = "ope_v36"
# Product-lock path (Jon/Steward 2026-08-12). Suite primary objective.
PRODUCT_PATH_PROFILE = "starlink_v1"

PRODUCT_GP_BAR = 75.0
PRODUCT_P95_BAR = 138.8
PRODUCT_TERR_GP_BAR = 77.0

PRODUCT_SEEDS = (13, 7, 42, 99, 123)
PRODUCT_DURATION_S = 90.0

ERA_OPE_V36 = "ope_v36"
ERA_STARLINK_V1 = "starlink_v1"
ERA_COUPLED_RNG = "coupled_rng"
# CSV replay era (v3.11). Not a generative profile; not the product default.
ERA_WETLINKS_V1 = "wetlinks_v1"


def resolve_path_profile(name: str | None) -> str:
    raw = (name or PRODUCT_PATH_PROFILE).strip().lower()
    if raw in ("product", "default", "starlink", "starlink_v1"):
        return PRODUCT_PATH_PROFILE
    if raw in ("research", "ope", "ope_v36"):
        return RESEARCH_PATH_PROFILE
    if raw in ("starlink_rtt", "ope_v36", "starlink_v1", "starlink_v2"):
        return raw
    raise ValueError(
        f"unknown path profile {name!r}; use starlink_v1 (product), "
        f"starlink_v2 (opt-in flicker research), or ope_v36 (research)"
    )


def apply_profile(cfg: LeoPathConfig, path_profile: str) -> LeoPathConfig:
    """Stamp a profile onto a config. Terrestrial paths ignore generative profile."""
    cfg.path_profile = RESEARCH_PATH_PROFILE if cfg.terrestrial else path_profile
    return cfg
