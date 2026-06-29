"""Status normalizer — DEPRECATED. Use domain.status_mapper directly.

.. deprecated:: Phase-7
    This module is a legacy shim. The circular dependency it was created to
    break has been resolved by inlining the lazy import in domain.enums.py.
    New code should import from :mod:`domain.status_mapper` directly.

    This module is kept temporarily for backward compatibility and will be
    removed in a future release.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from domain.types import OrderStatus


def normalize_status(broker_status: str) -> OrderStatus:
    """Normalize a broker-specific status string to canonical OrderStatus.

    .. deprecated:: Use ``StatusMapperRegistry.normalize()`` directly.
    """
    import warnings

    warnings.warn(
        "domain.status_normalizer.normalize_status is deprecated. "
        "Use domain.status_mapper.StatusMapperRegistry.normalize() instead.",
        DeprecationWarning,
        stacklevel=2,
    )
    from domain.status_mapper import StatusMapperRegistry

    return StatusMapperRegistry.normalize(broker_status)
