#!/usr/bin/env python3
"""ASCENT-D P9 outer frame: sync + RS(255,223) + erase-on-fail.

Implements the locked deep-space outer frame from SPEC C.5 / wave2-deep-space.
Uses reedsolo for RS_GF256. CRC-32C when available; else ISO-HDLC CRC-32
labeled as lab_crc32 (still erase-on-fail).

No RF transmit. No em/en dashes.
"""
from __future__ import annotations

import struct
import zlib
from dataclasses import dataclass
from typing import List, Optional, Tuple

from reedsolo import ReedSolomonError, RSCodec

try:
    import crc32c as _crc32c_mod  # type: ignore

    def crc32c_bytes(data: bytes) -> int:
        return int(_crc32c_mod.crc32c(data)) & 0xFFFFFFFF

    CRC_NAME = "CRC-32C"
except Exception:  # pragma: no cover

    def crc32c_bytes(data: bytes) -> int:
        # Lab fallback: zlib CRC-32 (not Castagnoli). Still used as integrity tag.
        return zlib.crc32(data) & 0xFFFFFFFF

    CRC_NAME = "CRC-32-lab-fallback"

SYNC = bytes([0xD5, 0xE5, 0xC0, 0xDE])
PROFILE_D = 0x44  # 'D'
PROFILE_E = 0x45
PROFILE_A = 0x41
FAMILY_RS = 0x01
FAMILY_NONE = 0x00
MAX_UNIT = 8192
RS_N, RS_K = 255, 223
RS_PARITY = RS_N - RS_K  # 32


class AscentDError(Exception):
    pass


@dataclass
class P9Frame:
    profile: int
    family: int
    n: int
    k: int
    interleave: int
    crc_pre: int
    unit: bytes
    raw: bytes


def _ecc_hdr(family: int = FAMILY_RS, interleave: int = 1, crc_pre: int = 1) -> bytes:
    return bytes([family, RS_N & 0xFF, RS_K & 0xFF, interleave & 0xFF, crc_pre & 0xFF])


def _protected_blob(profile: int, ecc: bytes, length_be: bytes, unit: bytes) -> bytes:
    """CRC over profile||ecc||len||unit, then crc||unit."""
    crc = crc32c_bytes(bytes([profile]) + ecc + length_be + unit)
    return struct.pack(">I", crc) + unit


def _rs_encode_blocks(protected: bytes, interleave: int = 1) -> bytes:
    """Encode protected bytes as RS(255,223) codewords (full n-byte words)."""
    rs = RSCodec(RS_PARITY)
    pad = (-len(protected)) % RS_K
    padded = protected + (b"\x00" * pad)
    codewords: List[bytes] = []
    for i in range(0, len(padded), RS_K):
        block = padded[i : i + RS_K]
        codewords.append(bytes(rs.encode(block)))
    # Lab interleave I=1: sequential. I>1: simple block interleave across up to I codewords.
    if interleave <= 1 or len(codewords) <= 1:
        return b"".join(codewords)
    # Row-column style: groups of up to I codewords, emit by column
    out = bytearray()
    for g in range(0, len(codewords), interleave):
        group = codewords[g : g + interleave]
        # pad group with zero codewords for rectangular write
        while len(group) < interleave:
            group.append(b"\x00" * RS_N)
        for col in range(RS_N):
            for row in range(len(group)):
                out.append(group[row][col])
    return bytes(out)


def _rs_decode_blocks(
    codeword_blob: bytes, expected_protected_len: int, interleave: int = 1
) -> Optional[bytes]:
    """Return protected bytes (unpadded) or None on uncorrectable error."""
    rs = RSCodec(RS_PARITY)
    n_blocks = (expected_protected_len + RS_K - 1) // RS_K
    need = n_blocks * RS_N
    if interleave > 1:
        # reverse column interleave in groups
        groups = []
        pos = 0
        remaining = n_blocks
        while remaining > 0:
            gsize = min(interleave, remaining)
            # each group wrote gsize * RS_N bytes (with pad rows if short - we used pad rows)
            take = interleave * RS_N
            chunk = codeword_blob[pos : pos + take]
            if len(chunk) < take:
                return None
            pos += take
            group = [bytearray(RS_N) for _ in range(interleave)]
            i = 0
            for col in range(RS_N):
                for row in range(interleave):
                    group[row][col] = chunk[i]
                    i += 1
            groups.extend([bytes(group[r]) for r in range(gsize)])
            remaining -= gsize
        words = groups
    else:
        if len(codeword_blob) < need:
            return None
        words = [
            codeword_blob[i : i + RS_N] for i in range(0, need, RS_N)
        ]

    protected = bytearray()
    try:
        for w in words[:n_blocks]:
            dec, _, _ = rs.decode(w)
            protected.extend(bytes(dec))
    except ReedSolomonError:
        return None
    return bytes(protected[:expected_protected_len])


def encode_p9(
    unit: bytes,
    profile: int = PROFILE_D,
    interleave: int = 1,
    family: int = FAMILY_RS,
) -> bytes:
    """Wrap a logical unit in an ASCENT-D P9 frame."""
    if len(unit) > MAX_UNIT:
        raise AscentDError(f"unit length {len(unit)} > MAX_UNIT {MAX_UNIT}")
    if profile == PROFILE_D and family == FAMILY_NONE:
        raise AscentDError("family NONE illegal on ASCENT-D")
    ecc = _ecc_hdr(family=family, interleave=interleave, crc_pre=1)
    length_be = struct.pack(">I", len(unit))
    protected = _protected_blob(profile, ecc, length_be, unit)
    codewords = _rs_encode_blocks(protected, interleave=interleave)
    return SYNC + bytes([profile]) + ecc + length_be + unit + codewords


def find_sync(stream: bytes, start: int = 0) -> int:
    return stream.find(SYNC, start)


def decode_p9(
    stream: bytes, start: int = 0
) -> Tuple[Optional[P9Frame], int, str]:
    """
    Decode one P9 frame starting at/after start.
    Returns (frame_or_None, next_index, status).
    status: ok | erased | no_sync | truncated
    """
    i = find_sync(stream, start)
    if i < 0:
        return None, start, "no_sync"
    j = i + 4
    if j + 1 + 5 + 4 > len(stream):
        return None, i + 1, "truncated"
    profile = stream[j]
    j += 1
    ecc = stream[j : j + 5]
    j += 5
    family, n, k, interleave, crc_pre = ecc[0], ecc[1], ecc[2], ecc[3], ecc[4]
    length = struct.unpack_from(">I", stream, j)[0]
    j += 4
    if length > MAX_UNIT:
        return None, i + 4, "erased"
    if j + length > len(stream):
        return None, i + 1, "truncated"
    unit = stream[j : j + length]
    j += length
    if profile == PROFILE_D and family == FAMILY_NONE:
        return None, i + 4, "erased"
    if family != FAMILY_RS or n != RS_N or k != RS_K:
        # only RS implemented in this lab
        return None, i + 4, "erased"

    protected_len = 4 + length  # crc + unit
    n_blocks = (protected_len + RS_K - 1) // RS_K
    if interleave <= 1:
        need = n_blocks * RS_N
    else:
        # groups of interleave rows
        full_groups = (n_blocks + interleave - 1) // interleave
        need = full_groups * interleave * RS_N
    if j + need > len(stream):
        return None, i + 1, "truncated"
    codeword_blob = stream[j : j + need]
    j_end = j + need

    protected = _rs_decode_blocks(codeword_blob, protected_len, interleave=interleave)
    if protected is None or len(protected) < 4:
        return None, i + 4, "erased"

    got_crc = struct.unpack_from(">I", protected, 0)[0]
    body = protected[4:]
    if len(body) != length:
        return None, i + 4, "erased"
    # Recovered body is authoritative after RS; CRC must match header binding.
    length_be = struct.pack(">I", length)
    expect = crc32c_bytes(bytes([profile]) + ecc + length_be + body)
    if crc_pre and got_crc != expect:
        return None, i + 4, "erased"

    frame = P9Frame(
        profile=profile,
        family=family,
        n=n,
        k=k,
        interleave=interleave,
        crc_pre=crc_pre,
        unit=body,
        raw=stream[i:j_end],
    )
    return frame, j_end, "ok"


def strip_to_earth(frame: P9Frame) -> bytes:
    """Earth re-emit: inner unit only (ASCENT-E logical bytes)."""
    return frame.unit
