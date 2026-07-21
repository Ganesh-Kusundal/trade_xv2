"""Dhan forever-order extension."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from domain.extensions.base import Extension
from domain.value_objects.capability import Capability
from domain.market_enums import ExchangeId

if TYPE_CHECKING:
    from domain.instruments.instrument_id import InstrumentId


class DhanForeverOrderExtension(Extension):
    def __init__(self, gateway: Any) -> None:
        self._gw = gateway
        self._symbol = ""
        self._exchange = "NSE"

    @property
    def name(self) -> str:
        return "forever_order"

    @property
    def broker(self) -> str:
        return "dhan"

    @property
    def version(self) -> str:
        return "1.0"

    @property
    def capabilities(self) -> tuple[Capability, ...]:
        return ()

    def is_available_for(self, instrument_id: InstrumentId) -> bool:
        return True

    def for_instrument(self, symbol: str, exchange: str = ExchangeId.NSE) -> DhanForeverOrderExtension:
        ext = DhanForeverOrderExtension(self._gw)
        ext._symbol = symbol
        ext._exchange = exchange
        return ext

    def place(self, *, quantity: int, price: Any = None, side: str = "BUY", **kwargs: Any) -> Any:
        fn = getattr(self._gw, "forever_order", None) or getattr(
            self._gw, "place_forever_order", None
        )
        if not callable(fn):
            raise RuntimeError("Dhan gateway has no forever_order capability wired")
        return fn(
            symbol=self._symbol,
            exchange=self._exchange,
            quantity=quantity,
            price=price,
            side=side,
            **kwargs,
        )
