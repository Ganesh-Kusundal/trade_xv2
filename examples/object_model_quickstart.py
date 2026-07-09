#!/usr/bin/env python3
"""Object-model quickstart — product API only (no gateway imports).

Run from repo root::

    PYTHONPATH=src:. python examples/object_model_quickstart.py

Uses paper broker by default (no credentials).
"""

from __future__ import annotations

from decimal import Decimal

import tradex


def main() -> None:
    session = tradex.connect("paper")
    try:
        # ── Epic 1: Market Access (data path) ─────────────────────────
        stock = session.universe.equity("RELIANCE")
        q = stock.refresh()
        print("quote:", None if q is None else f"ltp={q.ltp} bid={q.bid} ask={q.ask}")

        series = stock.history(timeframe="1D", days=5)
        print("history bars:", series.bar_count)

        handle = stock.subscribe()
        print("subscribe: live=", stock.is_live, "handle_active=", handle.is_active if handle else None)
        if handle is not None:
            handle.unsubscribe()

        # ── Epic 2 preview: OMS orders (sim only) ─────────────────────
        result = stock.buy(
            1,
            price=Decimal("2500"),
            correlation_id="quickstart:buy:1",
        )
        print(
            "buy:",
            result.success,
            getattr(result.order, "order_id", None) if result.order else result.error,
        )

        result2 = session.sell(stock, 1, price=Decimal("2501"))
        print("session.sell:", result2.success)

        # Bare instrument after connect resolves default provider
        from domain.instruments.instrument import Equity

        bare = Equity("INFY")
        try:
            bare.refresh()
            print("bare Equity after connect: ok")
        except Exception as exc:
            print("bare Equity:", type(exc).__name__, exc)

        # Option chain (paper may return empty — still exercises the API)
        try:
            idx = session.universe.index("NIFTY")
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
