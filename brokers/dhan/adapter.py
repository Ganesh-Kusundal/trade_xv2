from __future__ import annotations

"""Dhan → domain DataProvider adapter (broker as a plugin).

This is the ONLY place where Dhan's gateway meets the domain. It wraps
``brokers.dhan.gateway.BrokerGateway`` and normalizes its outputs into the
domain ``DataProvider`` protocol. The public ``markets`` API never imports
this module — it is wired exclusively at the composition root.
"""

from typing import TYPE_CHECKING, Any

from brokers.common.adapter_base import BaseDataAdapter

if TYPE_CHECKING:
    from domain.instruments.instrument_id import InstrumentId


class DhanDataAdapter(BaseDataAdapter):
    """Adapts a Dhan ``BrokerGateway`` to the domain ``DataProvider`` port."""

    def __init__(self, gateway: Any, *, broker_id: str = "dhan") -> None:
        super().__init__(gateway, broker_id=broker_id)

    def _get_depth_stream_method(self) -> str | None:
        """Dhan uses depth_20 for depth streaming."""
        return "depth_20"
