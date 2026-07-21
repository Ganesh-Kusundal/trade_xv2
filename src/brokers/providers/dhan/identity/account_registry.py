"""Backward-compatible re-export.

``AccountConnectionRegistry`` is broker-agnostic and now lives in
``brokers.common.identity.account_registry`` (Upstox uses it too).
Existing imports from this module continue to work unchanged.
"""

from __future__ import annotations

from brokers.common.identity.account_registry import AccountConnectionRegistry

__all__ = ["AccountConnectionRegistry"]
