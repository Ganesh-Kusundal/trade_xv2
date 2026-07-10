"""Deprecation helpers for the ``tradex.runtime`` backward-compat facade.

Production code must import from the canonical domain / application /
infrastructure modules. These facades remain only for gradual migration of
tests and external consumers.
"""

from __future__ import annotations

import warnings

_SEEN: set[str] = set()


def warn_facade(deprecated_module: str, canonical: str, *, once: bool = True) -> None:
    """Emit a :class:`DeprecationWarning` for a facade import.

    Parameters
    ----------
    deprecated_module:
        Fully-qualified facade module name (usually ``__name__``).
    canonical:
        Import path callers should use instead.
    once:
        If True, warn only once per process per ``deprecated_module``.
    """
    if once and deprecated_module in _SEEN:
        return
    _SEEN.add(deprecated_module)
    warnings.warn(
        f"{deprecated_module} is a deprecated compatibility facade; "
        f"import from {canonical} instead",
        DeprecationWarning,
        stacklevel=3,
    )
