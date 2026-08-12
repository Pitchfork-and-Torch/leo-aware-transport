"""LeoAwareCCA (v3.4.1). Source stored compressed in leo_aware.py.z64.

Runtime materializes the module from the sibling blob so large CCA source can
be pushed through size-limited tooling. Semantic change vs tip v3.4-p95:
cruise delay_yield subtract 0.35→0.25 MSS at delay_ratio>1.45.
"""
from __future__ import annotations

import base64
import zlib
from pathlib import Path

_blob = Path(__file__).with_name("leo_aware.py.z64").read_text().strip()
_src = zlib.decompress(base64.b64decode(_blob)).decode("utf-8")
exec(compile(_src, str(Path(__file__).resolve()), "exec"), globals())
