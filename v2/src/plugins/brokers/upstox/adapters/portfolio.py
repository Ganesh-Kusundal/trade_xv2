"""Upstox portfolio adapter."""

from __future__ import annotations

from typing import TYPE_CHECKING

from domain.entities import Account, Position
from plugins.brokers.upstox.wire import UpstoxWire

if TYPE_CHECKING:
    from plugins.brokers.common.transport import BaseTransport
    from plugins.brokers.upstox.config import UpstoxConfig


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

    def get_positions(self) -> list[Position]:
        data = self._transport.get("/portfolio/short-term-positions")
        rows = data if isinstance(data, list) else data.get("data", [])
        return [self._wire.to_position(r) for r in rows]

    def get_holdings(self) -> list[Position]:
        data = self._transport.get("/portfolio/long-term-holdings")
        rows = data if isinstance(data, list) else data.get("data", [])
        return [self._wire.to_position(r) for r in rows]

    def get_funds(self) -> Account:
        # v2 host path works; v3 also works with Api-Version header
        data = self._transport.get("/user/get-funds-and-margin")
        return self._wire.to_account(data if isinstance(data, dict) else {})

    def get_profile(self) -> dict:
        """Lightweight auth probe on v2."""
        data = self._transport.get("/user/profile")
        return data if isinstance(data, dict) else {}
