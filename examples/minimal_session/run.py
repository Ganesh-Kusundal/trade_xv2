#!/usr/bin/env python3
"""Minimal developer platform demo — connect → quote → disconnect."""

from __future__ import annotations

import tradex


def main() -> None:
    session = tradex.connect("paper")
    try:
        stock = session.universe.equity("RELIANCE")
        quote = stock.refresh()
        ltp = getattr(quote, "ltp", None) or stock.ltp
        print(f"paper RELIANCE ltp={ltp}")
        status = session.status
        print(
            f"mode={status.mode} orders_enabled={status.orders_enabled} "
            f"authenticated={status.authenticated}"
        )
    finally:
        if hasattr(session, "close"):
            session.close()


if __name__ == "__main__":
    main()
