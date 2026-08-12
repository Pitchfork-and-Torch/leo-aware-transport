"""LeoAwareCCA (v3.4.1). Source stored compressed in leo_aware.py.z64.[0-3].

Semantic change vs tip v3.4-p95: cruise delay_yield subtract 0.35→0.25 MSS.
"""
from __future__ import annotations

import base64
import zlib
from pathlib import Path

_dir = Path(__file__).parent
_blob = "".join((_dir / f"leo_aware.py.z64.{i}").read_text().strip() for i in range(4))
_src = zlib.decompress(base64.b64decode(_blob)).decode("utf-8")
exec(compile(_src, str(Path(__file__).resolve()), "exec"), globals())
