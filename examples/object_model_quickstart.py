#!/usr/bin/env python3
"""Object-model quickstart — BrokerSession + gateway public API.

Run from repo root::

    PYTHONPATH=src:. python examples/object_model_quickstart.py

Uses paper broker by default (no credentials).
"""

from __future__ import annotations

from decimal import Decimal

from brokers import BrokerSession
from domain.enums import OrderType, ProductType, Side
from domain.orders.requests import OrderRequest


def main() -> None:
    session = BrokerSession.connect("paper")
    try:
        stock = session.stock("RELIANCE")
        q = stock.refresh()
        print("quote:", None if q is None else f"ltp={q.ltp} bid={q.bid} ask={q.ask}")

        series = stock.history(timeframe="1D", days=5)
        print("history bars:", series.bar_count)

        handles = session.gateway.subscribe([stock])
        handle = handles[0] if handles else None
        print(
            "subscribe: live=",
            stock.is_live,
            "handle_active=",
            handle.is_active if handle else None,
        )
        session.gateway.unsubscribe([stock])

        result = session.gateway.place_order(
            OrderRequest(
                symbol="RELIANCE",
                exchange="NSE",
                transaction_type=Side.BUY,
                quantity=1,
                price=Decimal("2500"),
                order_type=OrderType.LIMIT,
                product_type=ProductType.INTRADAY,
                correlation_id="quickstart:buy:1",
            )
        )
        print(
            "place_order:",
            getattr(result, "success", None),
            getattr(result, "order_id", None)
            or getattr(getattr(result, "order", None), "order_id", None),
        )

        result2 = session.session.sell(stock, 1, price=Decimal("2501"))
        print("session.sell:", result2.success)

        from domain.instruments.instrument import Equity

        bare = Equity("INFY")
        try:
            bare.refresh()
            print("bare Equity after connect: ok")
        except Exception as exc:
            print("bare Equity:", type(exc).__name__, exc)

        try:
            idx = session.index("NIFTY")
            chain = idx.option_chain()
            print(
                "option_chain:",
                chain.underlying,
                "strikes=",
                len(chain.strikes),
                "atm=",
                None if chain.atm is None else chain.atm.strike,
            )
        except Exception as exc:
            print("option_chain skipped:", type(exc).__name__, exc)

    finally:
        session.close()
        print("session closed")


if __name__ == "__main__":
    main()
