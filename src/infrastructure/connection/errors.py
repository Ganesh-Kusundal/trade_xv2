"""Typed errors for broker connection bootstrap.

Re-exports from ``domain.errors`` for backward compatibility.
New code should import from ``domain.errors`` directly.
"""

from __future__ import annotations

from domain.errors import BrokerNotReadyError

__all__ = ["BrokerNotReadyError"]
