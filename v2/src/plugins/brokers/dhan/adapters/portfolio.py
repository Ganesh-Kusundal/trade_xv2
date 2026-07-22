"""Dhan portfolio — positions / holdings / funds."""

from __future__ import annotations

from typing import TYPE_CHECKING

from domain.entities import Account, Position
from plugins.brokers.dhan.wire import DhanWire

if TYPE_CHECKING:
    from plugins.brokers.common.transport import BaseTransport


class DhanPortfolioAdapter:
    def __init__(self, transport: BaseTransport, wire: DhanWire | None = None) -> None:
        self._transport = transport
        self._wire = wire or DhanWire()

    def get_positions(self) -> list[Position]:
        data = self._transport.get("/positions")
        rows = data if isinstance(data, list) else data.get("data", [])
        return [self._wire.to_position(r) for r in rows]

    def get_holdings(self) -> list[Position]:
        data = self._transport.get("/holdings")
        rows = data if isinstance(data, list) else data.get("data", [])
        return [self._wire.to_position(r) for r in rows]

    def get_funds(self) -> Account:
        data = self._transport.get("/fundlimit")
        return self._wire.to_account(data if isinstance(data, dict) else {})
