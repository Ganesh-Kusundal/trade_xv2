"""Upstox news extension — instrument.broker.news surface."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from domain.extensions.base import Extension
from domain.value_objects.capability import Capability

if TYPE_CHECKING:
    from domain.instruments.instrument_id import InstrumentId


class UpstoxNewsExtension(Extension):
    def __init__(self, gateway: Any) -> None:
        self._gw = gateway
        self._symbol = ""
        self._exchange = "NSE"

    @property
    def name(self) -> str:
        return "news"

    @property
    def broker(self) -> str:
        return "upstox"

    @property
    def version(self) -> str:
        return "1.0"

    @property
    def capabilities(self) -> tuple[Capability, ...]:
        return (Capability(name="news", supported=True),)

    def is_available_for(self, instrument_id: InstrumentId) -> bool:
        return True

    def for_instrument(self, symbol: str, exchange: str = "NSE") -> "UpstoxNewsExtension":
        ext = UpstoxNewsExtension(self._gw)
        ext._symbol = symbol
        ext._exchange = exchange
        return ext

    def fetch(self, *, limit: int = 20, **kwargs: Any) -> Any:
        """Fetch news for the bound symbol if gateway supports it."""
        for name in ("news", "get_news", "fetch_news", "symbol_news"):
            fn = getattr(self._gw, name, None)
            if callable(fn):
                try:
                    return fn(self._symbol, limit=limit, **kwargs)
                except TypeError:
                    try:
                        return fn(self._symbol, limit)
                    except TypeError:
                        return fn(self._symbol)
        raise RuntimeError("Upstox gateway has no news method wired")
