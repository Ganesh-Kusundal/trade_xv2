"""TradeX — institutional-grade algorithmic trading framework.

The user-facing namespace.  Usage::

    import tradex

    session = tradex.Session(broker="dhan")
    reliance = session.instruments.equity("RELIANCE")
    order = reliance.buy(qty=10, limit=2955.0)

This package will eventually hold the top-level ``Session``, ``Instrument``
hierarchy, and runtime kernel.  For now it owns ``tradex.runtime`` — the
honest platform kernel (migrated from ``brokers.common``).
"""

from __future__ import annotations
