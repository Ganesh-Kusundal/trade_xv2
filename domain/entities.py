"""Canonical domain dataclasses — value objects returned by broker adapters.

These are the single source of truth for every domain model that flows
through the system after the adapter boundary. DataFrames are used for
market data (OHLCV, quotes, option chain, depth); these dataclasses are
used for orders, positions, holdings, and trades.

**This is a re-export facade** (REF-025). The actual definitions live in
narrow submodules:

* :mod:`domain.orders` — ``Order``, ``OrderResponse``, ``Trade``, ``FieldMapping``
* :mod:`domain.positions` — ``Position``, ``Holding``
* :mod:`domain.account` — ``Balance``, ``FundLimits``
* :mod:`domain.market` — ``Quote``, ``MarketDepth``, ``DepthLevel``, ``Instrument``
* :mod:`domain.derivatives` — ``OptionContract``, ``OptionLeg``, ``OptionStrike``,
  ``OptionChain``, ``FutureContract``, ``FutureChain``
* :mod:`domain.alerts` — ``ConditionalAlert``, ``ConditionalAlertRequest``,
  ``MarketIntelligenceSnapshot``, ``PnlExitPolicy``, ``PnlExitResult``

Usage remains unchanged::

    from domain.entities import Order, Position

    order = Order(
        order_id="O-123",
        symbol="RELIANCE",
        exchange="NSE",
        side=Side.BUY,
        order_type=OrderType.LIMIT,
        quantity=10,
        price=Decimal("2500"),
    )
"""

from __future__ import annotations

from domain.account import Balance, FundLimits  # noqa: F401
from domain.alerts import (  # noqa: F401
    ConditionalAlert,
    ConditionalAlertRequest,
    MarketIntelligenceSnapshot,
    PnlExitPolicy,
    PnlExitResult,
)
from domain.derivatives import (  # noqa: F401
    FutureChain,
    FutureContract,
    OptionChain,
    OptionContract,
    OptionLeg,
    OptionStrike,
)

# Re-export domain enums that the original entities.py made accessible.
# Multiple callers (OMS, tests) import these from domain.entities rather than domain.types.
from domain.enums import (  # noqa: F401
    OrderStatus,
    OrderType,
    ProductType,
    Side,
    Validity,
)
from domain.market import DepthLevel, Instrument, MarketDepth, Quote  # noqa: F401
from domain.orders import FieldMapping, Order, OrderResponse, Trade  # noqa: F401
from domain.positions import Holding, Position  # noqa: F401
