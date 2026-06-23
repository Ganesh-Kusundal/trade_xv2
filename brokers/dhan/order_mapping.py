"""Dhan order field mapping — uses the shared :class:`DefaultFieldMapping`.

Dhan API responses use camelCase field names; :mod:`brokers.common.core.field_mapping`
already handles both camelCase and snake_case variants.
"""

from domain.field_mapping import DefaultFieldMapping

# Backward-compatible alias (REF-1).
DhanFieldMapping = DefaultFieldMapping

__all__ = ["DhanFieldMapping", "DefaultFieldMapping"]
