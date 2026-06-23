"""Upstox order field mapping — uses the shared :class:`DefaultFieldMapping`.

Upstox API responses use snake_case field names; :mod:`brokers.common.core.field_mapping`
already handles both camelCase and snake_case variants (including SL/SLM aliases).
"""

from brokers.common.core.field_mapping import DefaultFieldMapping

# Backward-compatible alias (REF-1).
UpstoxFieldMapping = DefaultFieldMapping

__all__ = ["UpstoxFieldMapping", "DefaultFieldMapping"]
