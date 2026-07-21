#!/usr/bin/env python3
"""Working example of Trade_XV2 brokers module usage.

Run from repo root::

    PYTHONPATH=src:. python examples/broker_usage_demo.py
"""

from __future__ import annotations

from datetime import date

import tradex


def main() -> None:
    # ── Connect (auto-authentication) ─────────────────────────────────────
    try:
        session = tradex.connect("paper")  # Use paper for demo (no creds needed)
        print(f"Connected: {session.describe()}")
    except Exception as exc:
        print(f"Connect failed: {exc}")
        return

    try:
        # ── Equity (NSE) ───────────────────────────────────────────────────────
        stock = session.universe.equity("RELIANCE")

        # Quote must be fetched first before accessing ltp property
        quote = stock.refresh()
        if quote:
            print(f"RELIANCE LTP: {stock.ltp}")  # Access property after refresh
        else:
            print("RELIANCE: No quote available (paper may return empty)")

        # Historical data - Keyword args required for history call
        try:
            history_series = stock.history(timeframe="15MIN", days=5)
            print(f"History bars: {history_series.bar_count}")
        except Exception as exc:
            print(f"History error: {type(exc).__name__}: {exc}")

        # 20-level depth (Dhan only - paper has no depth support)
        if stock.broker and stock.broker.has("depth20"):
            depth = stock.broker.depth20()
            print(f"Best bid: {depth.best_bid}")
            print(f"Best ask: {depth.best_ask}")
            print(f"Bid volume: {depth.bid_volume}")
        else:
            print("Depth20 not available (paper broker has no depth support)")

        # ── Index ─────────────────────────────────────────────────────────────
        idx = session.universe.index("NIFTY")
        try:
            chain = idx.option_chain(expiry="2026-07-31")
            if chain.atm:
                print(f"ATM Strike: {chain.atm.strike}")
            else:
                print("ATM: None (paper may return empty chain)")
            try:
                print(f"PCR: {chain.pcr()}")
            except Exception:
                print("PCR: N/A")
        except Exception as exc:
            print(f"Option chain error: {type(exc).__name__}: {exc}")

        # ── Futures ───────────────────────────────────────────────────────────
        try:
            future = session.universe.future("NIFTY", expiry=date(2026, 7, 30))
            basis = future.basis()
            if basis is not None:
                print(f"NIFTY Future Basis: {basis}")
            else:
                print("Future basis: None (spot or future price unavailable)")
        except Exception as exc:
            print(f"Future creation error: {type(exc).__name__}: {exc}")

        # ── Commodity Spot (MCX) ────────────────────────────────────────────
        try:
            spot = session.universe.spot("GOLD", exchange="MCX")
            history_series = spot.history(timeframe="1D", days=30)
            print(f"GOLD MCX history bars: {history_series.bar_count}")
        except Exception as exc:
            print(f"MCX spot error: {type(exc).__name__}: {exc}")

        # ── Live Streaming ─────────────────────────────────────────────────────
        # Note: Paper broker has limited/no streaming support
        def on_tick(quote_snapshot):
            if quote_snapshot:
                print(f"Tick update: {quote_snapshot.ltp}")

        try:
            # Prefer BrokerSession when available; tradex DomainSession has no gateway.
            if hasattr(session, "gateway"):
                handles = session.gateway.subscribe([stock], on_tick)
                handle = handles[0] if handles else None
            else:
                handle = stock._subscribe_core(on_tick)
            if handle:
                print(f"Subscribed: handle_active={handle.is_active}")
                if hasattr(session, "gateway"):
                    session.gateway.unsubscribe([stock])
                else:
                    handle.unsubscribe()
        except Exception as exc:
            print(f"Streaming error (expected for paper): {type(exc).__name__}")

        # ── Account / Portfolio ───────────────────────────────────────────────
        try:
            account = session.account
            # Refresh pulls data from execution provider
            account.refresh()
            print(f"Account funds: {account.funds}")  # Property, not method
            print(f"Account positions: {len(account.positions)}")
        except Exception as exc:
            print(f"Account error: {type(exc).__name__}")

        # ── Session Status ───────────────────────────────────────────────────
        print(f"Session status: {session.status.describe() if session.status else 'None'}")

    finally:
        session.close()
        print("Session closed")


if __name__ == "__main__":
    main()
