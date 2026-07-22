"""Ensure v2/src wins over parent-repo src/ on sys.path."""

from __future__ import annotations

import sys
from pathlib import Path

_V2_SRC = Path(__file__).resolve().parents[1] / "src"
_PARENT_SRC = Path(__file__).resolve().parents[2] / "src"

# Drop polluted domain modules loaded from parent src before our path pin.
for name in list(sys.modules):
    if name == "domain" or name.startswith("domain."):
        mod = sys.modules.get(name)
        origin = getattr(mod, "__file__", "") or ""
        if origin and str(_PARENT_SRC) in origin and str(_V2_SRC) not in origin:
            del sys.modules[name]

_v2 = str(_V2_SRC)
if _v2 in sys.path:
    sys.path.remove(_v2)
sys.path.insert(0, _v2)

_parent = str(_PARENT_SRC)
if _parent in sys.path:
    sys.path.remove(_parent)
