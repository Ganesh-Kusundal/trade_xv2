"""Instrument resolution methods for Session (resolve/quote_many/ltp_many/option_chain)."""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import TYPE_CHECKING, Any

from domain.constants.market import DEFAULT_EXCHANGE

if TYPE_CHECKING:
    from domain.instruments.instrument import Instrument


class SessionInstrumentMixin:
    """Instrument resolution, batch quotes, and option chain convenience."""

    def resolve(
        self,
        name: str,
        *,
        default_exchange: str = DEFAULT_EXCHANGE,
        default_year: int | None = None,
    ) -> Instrument:
        """Resolve a display or canonical name to a stamped :class:`Instrument`."""
        resolver = getattr(self, "_resolver", None)
        if resolver is not None:
            iid = resolver.resolve(
                name, default_exchange=default_exchange, default_year=default_year
            )
        else:
            from domain.instruments.display_names import parse_display_name

            iid = parse_display_name(
                name,
                default_exchange=default_exchange,
                default_year=default_year,
            )
        return self._universe.get(iid)

    def doctor(self, name: str) -> dict:
        """Name-resolution diagnostics (canonical, display, suggestions)."""
        resolver = getattr(self, "_resolver", None)
        if resolver is None:
            from domain.instruments.resolver import InstrumentResolver

            resolver = InstrumentResolver()
        return resolver.doctor(name)

    def instrument(
        self,
        name: str,
        *,
        default_exchange: str = DEFAULT_EXCHANGE,
        default_year: int | None = None,
    ) -> Instrument:
        """Alias for :meth:`resolve` — instrument-first entry by friendly name."""
        return self.resolve(
            name, default_exchange=default_exchange, default_year=default_year
        )

    def quote_many(
        self,
        names: list[str] | tuple[str, ...],
        *,
        default_exchange: str = DEFAULT_EXCHANGE,
    ) -> dict[str, Any]:
        """Refresh quotes for many display names → ``{name: QuoteSnapshot|None}``."""
        instruments: list[tuple[str, Instrument]] = []
        for name in names:
            instruments.append(
                (name, self.resolve(name, default_exchange=default_exchange))
            )

        ids = [inst.id for _, inst in instruments]
        batch_fn = getattr(self._provider, "get_quotes_batch", None)
        out: dict[str, Any] = {}
        if callable(batch_fn) and ids:
            try:
                quotes = list(batch_fn(ids))
                if len(quotes) == len(ids):
                    for (name, _inst), q in zip(instruments, quotes, strict=True):
                        out[name] = q
                    return out
            except Exception:
                pass

        for name, inst in instruments:
            try:
                out[name] = inst.refresh()
            except Exception:
                out[name] = None
        return out

    def ltp_many(
        self,
        names: list[str] | tuple[str, ...],
        *,
        default_exchange: str = DEFAULT_EXCHANGE,
    ) -> dict[str, Decimal | None]:
        """Last-traded prices for friendly names → ``{name: Decimal|None}``."""
        quotes = self.quote_many(names, default_exchange=default_exchange)
        result: dict[str, Decimal | None] = {}
        for name, q in quotes.items():
            if q is None:
                result[name] = None
                continue
            ltp = getattr(q, "ltp", None)
            if ltp is None:
                result[name] = None
            else:
                result[name] = ltp if isinstance(ltp, Decimal) else Decimal(str(ltp))
        return result

    def option_chain(
        self,
        underlying: str,
        *,
        expiry: date | int | str | None = None,
        exchange: str = DEFAULT_EXCHANGE,
    ):
        """Convenience: ``universe.index(underlying).option_chain(expiry=…)``."""
        return self._universe.index(underlying, exchange=exchange).option_chain(expiry)
