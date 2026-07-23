"""Upstox portfolio adapter."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from domain.entities import Account, Position
from plugins.brokers.upstox.wire import UpstoxWire
from shared.errors import MappingError

if TYPE_CHECKING:
    from plugins.brokers.common.transport import BaseTransport
    from plugins.brokers.upstox.config import UpstoxConfig

logger = logging.getLogger(__name__)


class UpstoxPortfolioAdapter:
    def __init__(
        self,
        transport: BaseTransport,
        wire: UpstoxWire | None = None,
        *,
        config: UpstoxConfig | None = None,
    ) -> None:
        self._transport = transport
        self._wire = wire or UpstoxWire()
        self._config = config

    def _to_positions(self, rows: list) -> list[Position]:
        positions: list[Position] = []
        for r in rows:
            try:
                positions.append(self._wire.to_position(r))
            except MappingError as exc:
                logger.warning("upstox_position_row_unmapped: %s", exc)
        return positions

    def get_positions(self) -> list[Position]:
        data = self._transport.get("/portfolio/short-term-positions")
        rows = data if isinstance(data, list) else data.get("data", [])
        return self._to_positions(rows)

    def get_holdings(self) -> list[Position]:
        data = self._transport.get("/portfolio/long-term-holdings")
        rows = data if isinstance(data, list) else data.get("data", [])
        return self._to_positions(rows)

    def get_funds(self) -> Account:
        # v2 host path works; v3 also works with Api-Version header
        data = self._transport.get("/user/get-funds-and-margin")
        return self._wire.to_account(data if isinstance(data, dict) else {})

    def get_profile(self) -> dict:
        """Lightweight auth probe on v2."""
        data = self._transport.get("/user/profile")
        return data if isinstance(data, dict) else {}
