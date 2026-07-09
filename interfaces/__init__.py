"""Deprecated scaffold (ENG-034) — do not import.

Canonical surfaces:

- SDK: ``tradex``
- REST: ``api``
- CLI: ``cli``
"""

from __future__ import annotations

import warnings

warnings.warn(
    "interfaces package is an empty scaffold; use tradex / api / cli (ENG-034).",
    DeprecationWarning,
    stacklevel=2,
)

__all__: list[str] = []
