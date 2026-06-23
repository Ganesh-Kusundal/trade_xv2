"""Status normalizer — breaks the cyclic dependency between enums.py ↔ status_mapper.py.

Previously ``OrderStatus.normalize()`` (in ``enums.py``) imported
``StatusMapperRegistry`` from ``status_mapper.py``, which imports
``OrderStatus`` from ``domain.types`` → ``enums.py``.  This compile-time
cycle is resolved by extracting the normalize logic into a free function in
this module that both ``OrderStatus`` and ``StatusMapperRegistry`` import from.

Usage::

    from domain.status_normalizer import normalize_status
    canonical = normalize_status("TRANSIT")  # → OrderStatus.OPEN
"""

from __future__ import annotations

from typing import ClassVar


# Lazy-imported by both enums.py and status_mapper.py.
# Using a module-level registry that status_mapper populates at import time.
_registry: object | None = None


def _get_registry():
    """Lazily return the StatusMapperRegistry class (avoids import cycle)."""
    global _registry
    if _registry is None:
        from domain.status_mapper import StatusMapperRegistry as R

        _registry = R
    return _registry


def normalize_status(broker_status: str) -> "OrderStatus":  # type: ignore[name-defined] # noqa: F821
    """Normalize a broker-specific status string to canonical OrderStatus.

    Delegates to :class:`~domain.status_mapper.StatusMapperRegistry.normalize`,
    which tries all registered broker mappings and falls back to OPEN.

    Args:
        broker_status: Raw status string from broker API (e.g. "TRANSIT", "EXECUTED").

    Returns:
        Canonical :class:`~domain.enums.OrderStatus` enum value.
    """
    registry = _get_registry()
    return registry.normalize(broker_status)
