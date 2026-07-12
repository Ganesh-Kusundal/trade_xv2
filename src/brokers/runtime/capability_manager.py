"""CapabilityManager — discovers broker capabilities for an instrument.

Thin coordinator over ``Instrument.capabilities`` / ``instrument.broker``.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from domain.instruments.instrument import Instrument


class CapabilityManager:
    """Reports which broker-specific capabilities an instrument supports."""

    def capabilities(self, instrument: Instrument) -> list[str]:
        return instrument.capabilities()

    def has(self, instrument: Instrument, name: str) -> bool:
        return instrument.has_extension(name)

    def get(self, instrument: Instrument, name: str):
        return instrument.get_extension(name)