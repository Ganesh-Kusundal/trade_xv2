"""Upstox extension providers for ExtensionRegistry."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

from domain.constants import DEFAULT_EXCHANGE
from domain.extensions.broker_bundle import ExtensionBundle
from domain.extensions.extended_order import ExtendedOrderExecutor
from domain.extensions.forever_order import (
    ForeverOrderProvider,
    ForeverOrderRequest,
    ForeverOrderResult,
)
from domain.extensions.fundamentals import (
    FinancialStatement,
    FundamentalsProvider,
    FundamentalsSnapshot,
)
from domain.extensions.news import NewsItem, NewsProvider
from domain.ports.broker_adapter import BrokerAdapter
from domain.ports.broker_gateway import QuotaToken


class UpstoxNewsExtension(NewsProvider):
    def __init__(self, gateway: BrokerAdapter) -> None:
        broker = getattr(gateway, "_broker", None)
        if broker is None:
            raise RuntimeError("Upstox gateway missing _broker reference")
        self._news = broker.news

    async def fetch_symbol_news(
        self, symbol: str, *, quota: QuotaToken, limit: int = 20
    ) -> Sequence[NewsItem]:
        raw_items = self._news.get_news(symbol=symbol)
        return self._normalize(raw_items[:limit])

    async def fetch_market_news(
        self, *, quota: QuotaToken, category: str | None = None, limit: int = 20
    ) -> Sequence[NewsItem]:
        raw_items = self._news.get_news(category=category or "holdings")
        return self._normalize(raw_items[:limit])

    @staticmethod
    def _normalize(raw_items: list) -> list[NewsItem]:
        items: list[NewsItem] = []
        for row in raw_items:
            if not isinstance(row, dict):
                continue
            published = row.get("timestamp") or row.get("published_at")
            if isinstance(published, str):
                try:
                    published_at = datetime.fromisoformat(published.replace("Z", "+00:00"))
                except ValueError:
                    published_at = datetime.now(tz=timezone.utc)
            else:
                published_at = datetime.now(tz=timezone.utc)
            items.append(
                NewsItem(
                    headline=str(row.get("headline") or row.get("title") or ""),
                    published_at=published_at,
                    broker_id="upstox",
                    summary=str(row.get("summary") or row.get("description") or ""),
                    symbols=tuple(row.get("symbols") or []),
                    category=str(row.get("category") or ""),
                    source=str(row.get("source") or ""),
                )
            )
        return items


class UpstoxFundamentalsExtension(FundamentalsProvider):
    def __init__(self, gateway: BrokerAdapter) -> None:
        self._extended = gateway.extended

    async def fetch_fundamentals(self, isin: str, *, quota: QuotaToken) -> FundamentalsSnapshot:
        ratios = self._extended.get_ratios(isin) if hasattr(self._extended, "get_ratios") else {}
        return FundamentalsSnapshot(
            isin=isin,
            symbol=isin,
            broker_id="upstox",
            pe_ratio=Decimal(str(ratios.get("pe", 0))) if ratios.get("pe") else None,
            pb_ratio=Decimal(str(ratios.get("pb", 0))) if ratios.get("pb") else None,
        )

    async def fetch_financials(
        self,
        isin: str,
        statement_type: str,
        *,
        quota: QuotaToken,
        periods: int = 4,
    ) -> Sequence[FinancialStatement]:
        fetcher = {
            "profit_loss": getattr(self._extended, "get_profit_loss", None),
            "balance_sheet": getattr(self._extended, "get_balance_sheet", None),
            "cash_flow": getattr(self._extended, "get_cash_flow", None),
        }.get(statement_type)
        if fetcher is None:
            return []
        rows = fetcher(isin) or []
        statements: list[FinancialStatement] = []
        for row in rows[:periods]:
            if not isinstance(row, dict):
                continue
            statements.append(
                FinancialStatement(
                    period=str(row.get("period", "")),
                    period_type=str(row.get("period_type", "annual")),
                    values={
                        k: Decimal(str(v))
                        for k, v in row.items()
                        if k not in {"period", "period_type"} and v is not None
                    },
                )
            )
        return statements


class UpstoxGttForeverOrderStrategy(ForeverOrderProvider):
    """Registry strategy — forever-order port backed by Upstox GTT adapter."""

    def __init__(self, gateway: BrokerAdapter) -> None:
        broker = getattr(gateway, "_broker", None)
        if broker is None:
            raise RuntimeError("Upstox gateway missing _broker reference")
        self._gtt = broker.gtt

    async def place_forever_order(
        self, request: ForeverOrderRequest, *, quota: object
    ) -> ForeverOrderResult:
        from domain.entities import Order
        from domain.enums import OrderType, ProductType, Side

        order = Order(
            symbol=request.symbol,
            exchange=request.exchange,
            side=request.side if isinstance(request.side, Side) else Side(str(request.side)),
            quantity=request.quantity,
            price=request.price1,
            order_type=OrderType.LIMIT,
            product_type=ProductType.CNC,
        )
        result = self._gtt.place_gtt_single(order, order_flag="ABOVE")
        order_id = str(getattr(result, "order_id", "") or "")
        return ForeverOrderResult(success=bool(order_id), order_id=order_id)

    async def cancel_forever_order(self, order_id: str, *, quota: object) -> ForeverOrderResult:
        cancel = getattr(self._gtt, "cancel_gtt", None) or getattr(self._gtt, "cancel", None)
        if cancel is None:
            return ForeverOrderResult(
                success=False, message="GTT cancel not available", order_id=order_id
            )
        cancel(order_id)
        return ForeverOrderResult(success=True, order_id=order_id)

    async def modify_forever_order(
        self,
        order_id: str,
        *,
        price1: Decimal | None = None,
        trigger1: Decimal | None = None,
        price2: Decimal | None = None,
        trigger2: Decimal | None = None,
        quota: object,
    ) -> ForeverOrderResult:
        return ForeverOrderResult(success=False, message="not implemented")


class UpstoxExtendedOrderExecutor(ExtendedOrderExecutor):
    """Sync executor for Upstox extended order types (DR-B1).

    Encapsulates exactly the operations Upstox supports through its broker
    adapters (``gtt``, ``alert``, ``cover``, ``slice``, ``kill_switch``,
    ``exit_all``). Upstox does not expose native super orders through this
    surface, so ``place_super_order`` falls through to the base
    ``UnsupportedExtensionError``.
    """

    broker_id = "upstox"

    def __init__(self, gateway: BrokerAdapter) -> None:
        self._gateway = gateway

    @property
    def _broker(self) -> Any:
        broker = getattr(self._gateway, "_broker", None)
        if broker is None:
            raise RuntimeError("Upstox gateway missing _broker reference")
        return broker

    def place_forever_order(self, payload: dict[str, Any]) -> Any:
        return self._broker.gtt.place_forever_order(payload)

    def place_trigger(self, payload: dict[str, Any]) -> Any:
        broker = self._broker
        if not hasattr(broker, "alert"):
            raise self._unsupported("conditional triggers")
        return broker.alert.place_alert(payload)

    def exit_all(self) -> Any:
        return self._broker.exit_all.exit_all()

    def place_gtt(self, payload: dict[str, Any]) -> Any:
        return self._broker.gtt.place_gtt_single(payload)

    def place_cover_order(self, payload: dict[str, Any]) -> Any:
        from domain.orders.requests import OrderRequest
        from domain.enums import (
            OrderType,
            ProductType,
            Side,
            Validity,
        )

        req = OrderRequest(
            symbol=payload.get("symbol", ""),
            exchange=payload.get("exchange", DEFAULT_EXCHANGE),
            transaction_type=Side(payload.get("side", "BUY")),
            quantity=int(payload.get("quantity", 0)),
            order_type=OrderType(payload.get("order_type", "MARKET")),
            product_type=ProductType(payload.get("product_type", "INTRADAY")),
            validity=Validity(payload.get("validity", "DAY")),
            price=Decimal(str(payload.get("price", "0"))),
        )
        return self._broker.cover.place_cover_order(
            req, Decimal(str(payload.get("stop_loss_price", "0")))
        )

    def place_slice_order(self, payload: dict[str, Any]) -> Any:
        from domain.orders.requests import SliceOrderRequest

        req = SliceOrderRequest(**payload)
        return self._broker.slice.place_slice_order(req)

    def set_kill_switch(self, payload: dict[str, Any]) -> Any:
        updates = payload.get("updates", [])
        return self._broker.kill_switch.set_status(updates)


def register_upstox_extensions(gateway: BrokerAdapter) -> ExtensionBundle:
    bundle = ExtensionBundle("upstox")
    bundle.register(NewsProvider, UpstoxNewsExtension(gateway))
    bundle.register(FundamentalsProvider, UpstoxFundamentalsExtension(gateway))
    bundle.register(ForeverOrderProvider, UpstoxGttForeverOrderStrategy(gateway))
    bundle.register(ExtendedOrderExecutor, UpstoxExtendedOrderExecutor(gateway))
    return bundle


# Register factory so brokers.common.adapters can find it without importing us
from domain.extensions.broker_bundle import register_extension_factory

register_extension_factory("upstox", register_upstox_extensions)
