"""Dhan portfolio — positions / holdings / funds."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from domain.entities import Account, Position
from plugins.brokers.dhan.wire import DhanWire
from shared.errors import MappingError

if TYPE_CHECKING:
    from plugins.brokers.common.transport import BaseTransport

logger = logging.getLogger(__name__)


class DhanPortfolioAdapter:
    def __init__(self, transport: BaseTransport, wire: DhanWire | None = None) -> None:
        self._transport = transport
        self._wire = wire or DhanWire()

    def _to_positions(self, rows: list) -> list[Position]:
        positions: list[Position] = []
        for r in rows:
            try:
                positions.append(self._wire.to_position(r))
            except MappingError as exc:
                logger.warning("dhan_position_row_unmapped: %s", exc)
        return positions

    def get_positions(self) -> list[Position]:
        data = self._transport.get("/positions")
        rows = data if isinstance(data, list) else data.get("data", [])
        return self._to_positions(rows)

    def get_holdings(self) -> list[Position]:
        data = self._transport.get("/holdings")
        rows = data if isinstance(data, list) else data.get("data", [])
        return self._to_positions(rows)

    def get_funds(self) -> Account:
        data = self._transport.get("/fundlimit")
        return self._wire.to_account(data if isinstance(data, dict) else {})
