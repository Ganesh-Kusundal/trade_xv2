"""ExchangeAdapter — pure domain port for exchange-specific conventions.

ADR-005. Carries the market conventions the datalake currently hardcodes
(NSE session hours, ``"NSE"`` exchange literals, paise/rupee scaling, tick and
lot sizes). Exchange plugins implement this port; the datalake reads conventions
ONLY through the active adapter, never from a hardcoded constant.

This is a pure domain port: no broker logic, no implementation, no imports from
``infrastructure`` or ``brokers``.
"""

from __future__ import annotations

from datetime import datetime, time
from typing import Protocol, runtime_checkable
from zoneinfo import ZoneInfo


@runtime_checkable
class ExchangeAdapter(Protocol):
    """Exchange-specific conventions, decoupled from any one market."""

    @property
    def exchange(self) -> str:
        """Canonical exchange code (e.g. ``"NSE"``)."""
        ...

    @property
    def timezone(self) -> str:
        """IANA timezone name for the exchange's local session."""
        ...

    @property
    def base_currency(self) -> str:
        """ISO currency of quoted prices (e.g. ``"INR"``)."""
        ...

    @property
    def price_scale(self) -> int:
        """Multiplier from the exchange's integer price unit to major units.

        E.g. ``100`` means a wire price of 12345 represents 123.45 in
        ``base_currency``. Datalake must use this instead of a ``"paise"``
        literal.
        """
        ...

    @property
    def tick_size(self) -> float:
        """Minimum price increment in ``base_currency``."""
        ...

    @property
    def lot_size(self) -> int:
        """Standard contract lot size for the exchange's F&O segment."""
        ...

    def normalize_symbol(self, symbol: str, exchange: str) -> str:
        """Return the canonical ``(symbol, exchange)``-keyed identifier.

        Centralizes the symbol/exchange naming rules the datalake currently
        bakes in, so no ``"NSE"`` literal leaks into data code.
        """
        ...


# Backward-compatible re-exports — concrete adapters moved to
# domain.market.exchange_adapters. Import from there in new code.
import warnings as _warnings

def __getattr__(name: str):
    _CONCRETE = {
        "NSEExchangeAdapter",
        "BSEExchangeAdapter",
        "MCXExchangeAdapter",
        "_EXCHANGE_REGISTRY",
        "get_exchange_adapter",
    }
    if name in _CONCRETE:
        from domain.market import exchange_adapters as _mod
        _warnings.warn(
            f"Importing {name!r} from domain.ports.exchange_adapter is deprecated. "
            f"Use domain.market.exchange_adapters instead.",
            DeprecationWarning,
            stacklevel=2,
        )
        return getattr(_mod, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
