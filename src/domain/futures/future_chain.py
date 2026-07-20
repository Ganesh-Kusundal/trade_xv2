"""FutureChain aggregate — composition of Future instruments (parallel to OptionChain)."""

from __future__ import annotations

from datetime import date, datetime
from typing import TYPE_CHECKING

from domain.entities.options import FutureChain as FutureChainVO
from domain.entities.options import FutureContract

if TYPE_CHECKING:
    from domain.instruments.instrument import Future
    from domain.ports.order_service import OrderServicePort
    from domain.ports.protocols import DataProvider


class FutureChain:
    """Rich query surface over futures contracts for an underlying.

    Each contract is exposed as a stamped :class:`Future` instrument — not
    raw gateway dicts.
    """

    def __init__(
        self,
        chain: FutureChainVO,
        *,
        data_provider: DataProvider | None = None,
        provider: DataProvider | None = None,
        order_service: OrderServicePort | None = None,
    ) -> None:
        self._chain = chain
        self._provider = data_provider or provider
        self._order_service = order_service

    @property
    def underlying(self) -> str:
        return self._chain.underlying

    @property
    def exchange(self) -> str:
        return self._chain.exchange

    @property
    def expiries(self) -> tuple[str, ...]:
        if self._chain.expiries:
            return self._chain.expiries
        return tuple(c.expiry for c in self._chain.contracts if c.expiry)

    @property
    def contracts(self) -> tuple[FutureContract, ...]:
        return self._chain.contracts

    def _parse_expiry(self, expiry: str | date | None) -> date | None:
        if expiry is None:
            return None
        if isinstance(expiry, date) and not isinstance(expiry, datetime):
            return expiry
        s = str(expiry)
        for fmt in ("%Y-%m-%d", "%Y%m%d"):
            try:
                return datetime.strptime(s, fmt).date()
            except ValueError:
                continue
        return None

    def _future_from_contract(self, contract: FutureContract) -> Future | None:
        from domain.instruments.instrument import Future

        exp = self._parse_expiry(contract.expiry)
        if exp is None:
            return None
        exch = self._chain.exchange or "NFO"
        sym = contract.symbol or self._chain.underlying
        fut = Future(
            sym,
            exch,
            expiry=exp,
            data_provider=self._provider,
        )
        if self._order_service is not None:
            fut._bind_session_ports(
                data_provider=self._provider,
                order_service=self._order_service,
            )
        return fut

    def all(self) -> list[Future]:
        """All contracts as Future instruments."""
        out: list[Future] = []
        for c in self._chain.contracts:
            f = self._future_from_contract(c)
            if f is not None:
                out.append(f)
        return out

    def front(self) -> Future | None:
        """Nearest expiry Future (front month)."""
        items = self.all()
        if not items:
            return None
        return min(items, key=lambda f: f.expiry or date.max)

    def at_expiry(self, expiry: date | str) -> Future | None:
        target = self._parse_expiry(expiry)
        if target is None:
            return None
        for f in self.all():
            if f.expiry == target:
                return f
        return None

    def expiry_at(self, offset: int = 0) -> date | None:
        """0 = front, 1 = next, …"""
        offs = int(offset)
        if offs < 0:
            raise ValueError("offset must be >= 0")
        dates = sorted({self._parse_expiry(e) for e in self.expiries} - {None})  # type: ignore[arg-type]
        dates = [d for d in dates if d is not None]
        today = date.today()
        future = sorted(d for d in dates if d >= today)
        ordered = future if future else sorted(dates)
        if offs >= len(ordered):
            raise ValueError(f"expiry offset {offs} out of range ({len(ordered)} expiries)")
        return ordered[offs]

    def at_offset(self, offset: int = 0) -> Future | None:
        exp = self.expiry_at(offset)
        return self.at_expiry(exp) if exp else None

    def __len__(self) -> int:
        return len(self._chain.contracts)

    def __repr__(self) -> str:
        return (
            f"FutureChain(underlying={self._chain.underlying}, "
            f"contracts={len(self._chain.contracts)})"
        )
