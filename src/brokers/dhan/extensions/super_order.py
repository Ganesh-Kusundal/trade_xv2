"""Dhan super-order (bracket) extension — instrument.broker.super_order surface."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from domain.constants.exchanges import NSE
from domain.extensions.base import Extension
from domain.value_objects.capability import Capability

if TYPE_CHECKING:
    from domain.instruments.instrument_id import InstrumentId


class DhanSuperOrderExtension(Extension):
    """Expose Dhan super/bracket order capability without gateway imports in strategies."""

    def __init__(self, gateway: Any) -> None:
        self._gw = gateway
        self._symbol = ""
        self._exchange = NSE

    @property
    def name(self) -> str:
        return "super_order"

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

    def for_instrument(self, symbol: str, exchange: str = NSE) -> DhanSuperOrderExtension:
        ext = DhanSuperOrderExtension(self._gw)
        ext._symbol = symbol
        ext._exchange = exchange
        return ext

    def place(
        self,
        *,
        quantity: int,
        entry_price: Any,
        target_price: Any,
        stop_loss_price: Any,
        side: str = "BUY",
        **kwargs: Any,
    ) -> Any:
        """Place super/bracket order via gateway if supported."""
        fn = getattr(self._gw, "super_order", None) or getattr(self._gw, "place_super_order", None)
        if not callable(fn):
            raise RuntimeError("Dhan gateway has no super_order capability wired")
        return fn(
            symbol=self._symbol,
            exchange=self._exchange,
            quantity=quantity,
            entry_price=entry_price,
            target_price=target_price,
            stop_loss_price=stop_loss_price,
            side=side,
            **kwargs,
        )
