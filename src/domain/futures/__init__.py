"""Futures domain — re-exports Future from instruments.

The Future value object has been consolidated into domain.instruments.instrument.Future
to eliminate duplication. This module re-exports it for backward compatibility.
"""

from __future__ import annotations

from domain.entities.options import FutureChain, FutureContract
from domain.instruments.instrument import Future

__all__ = ["Future", "FutureChain", "FutureContract"]
