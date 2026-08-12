"""
ASCENT path-hint channel with optional ASCENT-D integrity (erase-on-fail).

Path hints are greppable ASCII agent-style units. Critical control is wrapped
in ASCENT-D P9 (RS(255,223) + CRC + fail-closed). Never apply a corrupted unit.

Wire shape (inner unit, sacred-ASCII friendly):
  ASCENT/1.0
  ROLE:pilot
  PATHHINT reconfig=1 epoch=3 cap_bps=80000000 rtt_s=0.045 freeze_s=0.12 next_cap_bps=70000000

Outer: ASCENT-D encode_p9(unit) when integrity protection is requested.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Tuple

from leo_cc.ascent_d import encode_p9, decode_p9, SYNC, PROFILE_D


@dataclass
class PathHint:
    """Decoded control fields for LeoAware.on_path_hint."""

    reconfigured: bool = False
    capacity_bps: Optional[float] = None
    rtt_s: Optional[float] = None
    epoch: Optional[int] = None
    freeze_remaining_s: Optional[float] = None
    freeze_active: Optional[bool] = None
    next_capacity_bps: Optional[float] = None
    role: str = "untrusted"
    integrity: str = "ok"  # ok | erased | no_sync | truncated | plain_ok


def encode_path_hint_unit(
    *,
    reconfigured: bool = False,
    capacity_bps: Optional[float] = None,
    rtt_s: Optional[float] = None,
    epoch: Optional[int] = None,
    freeze_remaining_s: Optional[float] = None,
    freeze_active: Optional[bool] = None,
    next_capacity_bps: Optional[float] = None,
    role: str = "pilot",
) -> bytes:
    """Build a greppable ASCENT path-hint unit (P0-style text, all bytes < 0x80)."""
    parts = [
        "ASCENT/1.0",
        f"ROLE:{role}",
        (
            "PATHHINT"
            f" reconfig={1 if reconfigured else 0}"
            f" epoch={epoch if epoch is not None else -1}"
            f" cap_bps={int(capacity_bps) if capacity_bps else 0}"
            f" rtt_s={float(rtt_s) if rtt_s is not None else 0.0:.6f}"
            f" freeze_s={float(freeze_remaining_s or 0.0):.6f}"
            f" freeze_active={1 if freeze_active else 0}"
            f" next_cap_bps={int(next_capacity_bps) if next_capacity_bps else 0}"
        ),
    ]
    unit = "\n".join(parts).encode("ascii")
    if any(b >= 0x80 for b in unit):
        raise ValueError("path-hint unit must stay sacred-ASCII (< 0x80)")
    return unit


def encode_path_hint_ascent_d(**fields) -> bytes:
    """Encode path hint as ASCENT-D P9 outer frame (integrity protected)."""
    unit = encode_path_hint_unit(**fields)
    return encode_p9(unit, profile=PROFILE_D, interleave=1)


def parse_path_hint_unit(unit: bytes) -> PathHint:
    """Parse inner path-hint unit. Fail soft: missing fields stay None."""
    text = unit.decode("ascii", errors="strict")
    role = "untrusted"
    reconfigured = False
    capacity_bps: Optional[float] = None
    rtt_s: Optional[float] = None
    epoch: Optional[int] = None
    freeze_remaining_s: Optional[float] = None
    freeze_active: Optional[bool] = None
    next_capacity_bps: Optional[float] = None

    for line in text.splitlines():
        line = line.strip()
        if line.startswith("ROLE:"):
            role = line[5:].strip() or "untrusted"
            continue
        if not line.startswith("PATHHINT"):
            continue
        # token parse: key=value pairs after PATHHINT
        tokens = line.split()[1:]
        kv: dict[str, str] = {}
        for tok in tokens:
            if "=" in tok:
                k, v = tok.split("=", 1)
                kv[k] = v
        reconfigured = kv.get("reconfig", "0") in ("1", "true", "True")
        if "epoch" in kv and kv["epoch"] not in ("-1", ""):
            try:
                epoch = int(kv["epoch"])
            except ValueError:
                epoch = None
        if "cap_bps" in kv:
            try:
                c = float(kv["cap_bps"])
                capacity_bps = c if c > 0 else None
            except ValueError:
                pass
        if "rtt_s" in kv:
            try:
                r = float(kv["rtt_s"])
                rtt_s = r if r > 0 else None
            except ValueError:
                pass
        if "freeze_s" in kv:
            try:
                freeze_remaining_s = max(0.0, float(kv["freeze_s"]))
            except ValueError:
                pass
        if "freeze_active" in kv:
            freeze_active = kv["freeze_active"] in ("1", "true", "True")
        if "next_cap_bps" in kv:
            try:
                n = float(kv["next_cap_bps"])
                next_capacity_bps = n if n > 0 else None
            except ValueError:
                pass

    if freeze_remaining_s is not None and freeze_remaining_s > 0:
        freeze_active = True

    return PathHint(
        reconfigured=reconfigured,
        capacity_bps=capacity_bps,
        rtt_s=rtt_s,
        epoch=epoch,
        freeze_remaining_s=freeze_remaining_s,
        freeze_active=freeze_active,
        next_capacity_bps=next_capacity_bps,
        role=role,
        integrity="ok",
    )


def decode_ascent_d_path_hint(
    stream: bytes, start: int = 0
) -> Tuple[Optional[PathHint], int, str]:
    """
    Decode one ASCENT-D protected path hint with erase-on-fail.

    Returns (hint_or_None, next_offset, status).
    status: ok | erased | no_sync | truncated
    On any integrity failure: never return a usable PathHint (erase).
    """
    frame, nxt, status = decode_p9(stream, start)
    if status != "ok" or frame is None:
        return None, nxt, status
    try:
        hint = parse_path_hint_unit(frame.unit)
    except (UnicodeDecodeError, ValueError):
        return None, nxt, "erased"
    hint.integrity = "ok"
    return hint, nxt, "ok"


def decode_plain_path_hint(unit: bytes) -> PathHint:
    """Decode unprotected ASCII unit (no ASCENT-D). Integrity = plain_ok."""
    hint = parse_path_hint_unit(unit)
    hint.integrity = "plain_ok"
    return hint


@dataclass
class IngestStats:
    ok: int = 0
    erased: int = 0
    no_sync: int = 0
    truncated: int = 0
    role_rejected: int = 0
    applied: int = 0


def ingest_path_hint_stream(
    cca,
    stream: bytes,
    now: float,
    *,
    trusted_roles: tuple[str, ...] = ("pilot", "gateway"),
    allow_untrusted_crosscheck: bool = False,
    stats: Optional[IngestStats] = None,
) -> IngestStats:
    """
    Fail-closed ingest of ASCENT-D frames into cca.on_path_hint.

    Never acts on erased / missing / role-rejected units.
    """
    stats = stats or IngestStats()
    offset = 0
    if not stream:
        stats.no_sync += 1
        return stats

    while offset < len(stream):
        # Hunt next sync; if none, stop
        if SYNC not in stream[offset:]:
            if offset == 0:
                stats.no_sync += 1
            break
        hint, nxt, status = decode_ascent_d_path_hint(stream, offset)
        if status == "ok" and hint is not None:
            stats.ok += 1
            role_ok = hint.role in trusted_roles or (
                allow_untrusted_crosscheck and hint.role == "untrusted"
            )
            if not role_ok:
                stats.role_rejected += 1
                offset = max(nxt, offset + 1)
                continue
            # Apply only integrity-ok units
            if hasattr(cca, "on_path_hint"):
                cca.on_path_hint(
                    now,
                    hint.reconfigured,
                    capacity_bps=hint.capacity_bps,
                    rtt_s=hint.rtt_s,
                    epoch=hint.epoch,
                    freeze_remaining_s=hint.freeze_remaining_s,
                    freeze_active=hint.freeze_active,
                    next_capacity_bps=hint.next_capacity_bps,
                )
                stats.applied += 1
            offset = max(nxt, offset + 1)
        elif status == "erased":
            stats.erased += 1
            offset = max(nxt, offset + 1)
        elif status == "truncated":
            stats.truncated += 1
            break
        elif status == "no_sync":
            stats.no_sync += 1
            break
        else:
            offset = max(nxt, offset + 1)
    return stats


def bit_flip_noise(frame: bytes, n_flips: int, rng) -> bytes:
    """Corrupt n random bits (for ASCENT-D erase tests)."""
    if n_flips <= 0 or not frame:
        return frame
    ba = bytearray(frame)
    nbits = len(ba) * 8
    for _ in range(n_flips):
        bit = int(rng.randrange(nbits))
        ba[bit // 8] ^= 1 << (bit % 8)
    return bytes(ba)
