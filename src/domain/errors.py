"""Domain-level error types -- backward-compatibility shim.

All error classes now live in :mod:`domain.exceptions`. This module re-exports
them so that existing ``from domain.errors import BrokerError`` imports
continue to work without modification. New code should import from
``domain.exceptions`` directly.
"""

from __future__ import annotations

from domain.exceptions import *  # noqa: F401,F403 -- re-exports
from domain.exceptions import TradeXV2RecoverableError  # noqa: F401 -- re-export
