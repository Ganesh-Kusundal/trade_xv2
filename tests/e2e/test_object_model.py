"""E2E: tradex public object model on paper gateway (no mocks)."""

from __future__ import annotations

from decimal import Decimal

import tradex
from brokers.paper import PaperGateway


def test_tradex_session_paper_equity_ltp() -> None:
    gw = PaperGateway()
    session = tradex.Session(broker="paper", gateway=gw)
    reliance = session.universe.equity("RELIANCE")
    assert reliance.symbol == "RELIANCE"
    assert reliance.exchange == "NSE"
    quote = reliance.refresh()
    assert quote is not None
    assert reliance.ltp is not None
    assert reliance.ltp > 0
    session.close()


def test_tradex_connect_paper_buy() -> None:
    """Paper buy path: OrderIntent → Risk → OMS → PaperExecutionProvider."""
    session = tradex.connect("paper")
    assert session.execution_provider is not None
    assert session.execution_provider.name == "paper"
    assert session.order_service is not None  # Wave C: OMS always wired

    reliance = session.universe.equity("RELIANCE")
    result = session.buy(reliance, 10, price=Decimal("2500"))
    assert result.success is True
    assert result.order is not None
    assert result.order.order_id
    # OMS stamps correlation onto the book order
    assert result.order.correlation_id

    market_result = session.market(reliance, 5, side="SELL")
    assert market_result.success is True
    session.close()


def test_tradex_connect_paper_oms_idempotent() -> None:
    session = tradex.connect("paper")
    reliance = session.universe.equity("RELIANCE")
    intent = session.intent(
        reliance, "BUY", 1, price=Decimal("100"), correlation_id="e2e:idem-1"
    )
    r1 = session.place(intent)
    r2 = session.place(intent)
    assert r1.success and r2.success
    assert r1.order.order_id == r2.order.order_id
    session.close()


def test_tradex_exports() -> None:
    assert tradex.Equity is not None
    assert tradex.Option is not None
    assert tradex.Universe is not None
    assert callable(tradex.Session)
    assert tradex.connect is tradex.open_session
    assert tradex.Session is tradex.open_session
