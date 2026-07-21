"""BrokerGateway — public broker-operations facade.

Owns trading, portfolio, and streaming subscription. Market data lives on
``Instrument`` (quote / history / depth), not here.

Usage::

    session = BrokerSession.connect("paper")
    reliance = session.stock("RELIANCE")
    session.gateway.subscribe([reliance])
    session.gateway.place_order(OrderRequest(...))
    session.gateway.positions()
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from typing import TYPE_CHECKING, Any

from domain.orders.requests import OrderRequest

if TYPE_CHECKING:
    from brokers.runtime.bundle import RuntimeBundle
    from domain.entities.account import Balance
    from domain.instruments.instrument import Instrument
    from domain.universe import Session as DomainSession


class BrokerGateway:
    """Thin facade over RuntimeBundle execution/subscriptions + account portfolio.

    Never returns SDK models or broker-native security IDs.
    """

    def __init__(self, runtime: RuntimeBundle, session: DomainSession) -> None:
        self._runtime = runtime
        self._session = session

    # ── Orders (OMS spine — same path as historical session.buy) ──────

    def place_order(self, request: OrderRequest) -> Any:
        """Place via OrderIntent → OMS → ExecutionProvider (ADR-0012 paper path)."""
        from decimal import Decimal

        from brokers.services._session import check_live_actionable
        from domain.enums import OrderType
        from domain.value_objects.price import snap_to_tick

        broker_id = getattr(getattr(self._session, "status", None), "broker_id", "paper")
        check_live_actionable(broker_id)

        instrument = self._resolve_instrument(request.symbol, request.exchange)
        price = request.price if request.price and request.price > 0 else None
        # MARKET risk sizing needs a ref price; use tick-aligned LTP when omitted.
        # (Risk has no instrument_provider on standalone paper OMS.)
        if price is None and request.order_type == OrderType.MARKET:
            try:
                instrument.refresh()
            except Exception:
                pass
            ltp = getattr(instrument, "ltp", None)
            if ltp is not None:
                try:
                    cand = ltp if isinstance(ltp, Decimal) else Decimal(str(ltp))
                    if cand > 0:
                        tick = getattr(instrument, "tick_size", None)
                        price = (
                            snap_to_tick(cand, Decimal(str(tick)))
                            if tick is not None and Decimal(str(tick)) > 0
                            else cand
                        )
                except Exception:
                    pass
        intent = self._session.intent(
            instrument,
            request.transaction_type,
            request.quantity,
            price=price,
            order_type=request.order_type,
            product_type=request.product_type,
            trigger_price=request.trigger_price,
            correlation_id=request.correlation_id,
        )
        return self._session.place(intent)

    def modify_order(self, order_id: str, **changes: Any) -> Any:
        return self._session.modify(order_id, **changes)

    def cancel_order(self, order_id: str) -> Any:
        return self._session.cancel(order_id)

    def orders(self) -> list[Any]:
        execution = self._runtime.execution
        if execution is not None:
            return list(execution.orders())
        return list(self._session.orders())

    # ── Portfolio ─────────────────────────────────────────────────────

    def positions(self) -> list[Any]:
        account = self._session.account
        if not account.is_refreshed:
            account.refresh()
        return list(account.positions)

    def holdings(self) -> list[Any]:
        account = self._session.account
        if not account.is_refreshed:
            account.refresh()
        return list(account.holdings)

    def funds(self) -> Balance | None:
        account = self._session.account
        if not account.is_refreshed:
            account.refresh()
        return account.funds

    def margin(self) -> Balance | None:
        """Account margin snapshot (Balance.used_margin / total_margin)."""
        # ponytail: margin mirrors funds until a dedicated MarginProvider is
        # wired on every broker; upgrade = call MarginProvider.calculate_margin
        return self.funds()

    # ── Streaming ─────────────────────────────────────────────────────

    def subscribe(
        self,
        instruments: Sequence[Instrument] | Instrument,
        callback: Callable | None = None,
        *,
        depth: bool = False,
    ) -> list[Any]:
        """Subscribe one or more instruments; returns handles (may include None)."""
        items = self._as_list(instruments)
        handles: list[Any] = []
        for inst in items:
            handles.append(
                self._runtime.subscriptions.subscribe(inst, callback, depth=depth)
            )
        return handles

    def unsubscribe(
        self,
        instruments: Sequence[Instrument] | Instrument,
    ) -> None:
        for inst in self._as_list(instruments):
            self._runtime.subscriptions.unsubscribe(inst)

    # ── Helpers ───────────────────────────────────────────────────────

    def _resolve_instrument(self, symbol: str, exchange: str) -> Instrument:
        universe = self._session.universe
        # Equity is the default cash instrument; options/futures callers should
        # pass a pre-built instrument via session factories + OrderRequest.symbol
        # that matches an equity for the OMS spine today.
        return universe.equity(symbol, exchange)

    @staticmethod
    def _as_list(instruments: Sequence[Instrument] | Instrument) -> list[Instrument]:
        if isinstance(instruments, (list, tuple)):
            return list(instruments)
        return [instruments]  # type: ignore[list-item]


__all__ = ["BrokerGateway"]
