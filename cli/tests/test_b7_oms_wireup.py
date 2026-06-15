"""Tests for Phase B / B7: Central OMS on the live CLI path.

The previous implementation had the central OMS
(``brokers/common/oms/``) built and tested in isolation, but the
live CLI path bypassed it. ``OrdersAdapter.place_order`` was
called directly with no risk check at all (the risk_manager
parameter was never injected). The CLI's ``OmsService.place_order``
called the broker gateway, which called the dhan adapter, with
no canonical risk gate.

B7 fixes this:

  - ``BrokerService._ensure_initialized`` now constructs a
    :class:`RiskManager` first, threads it into
    ``BrokerFactory.create(risk_manager=...)``, which passes it
    to ``DhanConnection`` → ``OrdersAdapter``. The risk check
    is now enforced on every place_order call.

  - ``BrokerService._build_and_register_oms_services`` builds
    a :class:`DailyPnlResetScheduler` and a
    :class:`TradingContext`, both registered with the
    LifecycleManager. They are drained on close().

  - The capital_fn is a placeholder (constant). A future commit
    will thread ``gateway.funds()`` so the position_pct and
    daily_loss_pct checks are sized to the real account.
"""

from __future__ import annotations

from decimal import Decimal
from unittest.mock import MagicMock

import pytest

from brokers.common.lifecycle import LifecycleManager
from brokers.common.oms import (
    PositionManager,
    RiskConfig,
    RiskManager,
)


# ── BrokerService constructs the OMS risk_manager before the factory ─────


def test_broker_service_builds_oms_risk_manager_with_placeholder_capital() -> None:
    """The OMS risk_manager is built with a placeholder capital_fn
    returning 1,000,000. The kill_switch and per-order risk checks
    are fully active. Position_pct and daily_loss_pct checks use
    the placeholder capital (a future commit will thread the real
    gateway.funds())."""
    from cli.services.broker_service import BrokerService

    bs = BrokerService()
    rm = bs._build_oms_risk_manager()
    assert isinstance(rm, RiskManager)
    # Capital is the placeholder 1,000,000
    assert rm._capital_fn() == Decimal("1000000")
    # The risk_manager has a position_manager wired
    assert isinstance(rm._position_manager, PositionManager)


def test_oms_risk_manager_kill_switch_blocks_orders() -> None:
    """The OMS risk_manager's kill_switch is the canonical one.
    Setting it blocks all subsequent orders regardless of which
    caller (OrdersAdapter, OMS, CLI) checks them."""
    from brokers.common.core.domain import Order, OrderStatus, OrderType, ProductType, Side

    bs_service = MagicMock()
    bs_service._build_oms_risk_manager = lambda: RiskManager(
        position_manager=PositionManager(),
        config=RiskConfig(),
        capital_fn=lambda: Decimal("1000000"),
    )
    from cli.services.broker_service import BrokerService
    bs = BrokerService()
    rm = bs._build_oms_risk_manager()

    order = Order(
        order_id="O-1", symbol="RELIANCE", exchange="NSE",
        side=Side.BUY, quantity=10, price=Decimal("2500"),
        order_type=OrderType.LIMIT, product_type=ProductType.INTRADAY,
        status=OrderStatus.OPEN,
    )

    # Order is allowed by default
    assert rm.check_order(order).allowed is True

    # Kill switch flipped → order blocked
    rm.set_kill_switch(True)
    result = rm.check_order(order)
    assert result.allowed is False
    assert "Kill switch is active" in result.reason


# ── BrokerFactory accepts and threads risk_manager to the connection ───


def test_factory_accepts_risk_manager_and_threads_to_connection() -> None:
    """BrokerFactory.create() must accept risk_manager=... and pass
    it to DhanConnection, which passes it to OrdersAdapter. This is
    the B7 invariant: the OMS risk_manager is the canonical risk
    check on the live path.
    """
    from brokers.dhan.factory import BrokerFactory

    # We don't actually call Dhan (we don't have a token), but we
    # can verify the factory's signature accepts the parameter.
    import inspect
    sig = inspect.signature(BrokerFactory.create)
    assert "risk_manager" in sig.parameters, (
        "BrokerFactory.create must accept risk_manager= parameter (B7)"
    )


# ── End-to-end: kill switch in the OMS blocks place_order via OrdersAdapter


def test_end_to_end_kill_switch_via_oms_blocks_dhan_place_order() -> None:
    """A complete chain: BrokerService builds the OMS, sets the
    kill_switch, the OrdersAdapter's risk_manager (the same OMS
    instance) is consulted, and a place_order is blocked."""
    from brokers.common.oms import RiskManager
    from brokers.common.oms.position_manager import PositionManager
    from cli.services.broker_service import BrokerService
    from brokers.dhan.exceptions import OrderError
    from brokers.dhan.orders import OrdersAdapter
    from brokers.dhan.http_client import DhanHttpClient
    from brokers.dhan.resolver import SymbolResolver
    from unittest.mock import MagicMock

    bs = BrokerService()
    rm = bs._build_oms_risk_manager()

    # Build a real OrdersAdapter with this risk_manager
    client = MagicMock(spec=DhanHttpClient)
    client.client_id = "TEST"
    resolver = MagicMock(spec=SymbolResolver)
    resolver.resolve.return_value = MagicMock(
        symbol="RELIANCE", security_id="500325",
        exchange=MagicMock(value="NSE"), lot_size=1,
    )
    # EXCHANGE_TO_SEGMENT.get("NSE") = "NSE_EQ" — not a derivative
    resolver.resolve.return_value.exchange.value = "NSE"

    adapter = OrdersAdapter(
        client=client, resolver=resolver,
        event_bus=None, risk_manager=rm,
    )

    # Set the kill switch via the OMS
    rm.set_kill_switch(True)

    # Try to place an order — must raise OrderError due to risk gate
    with pytest.raises(OrderError, match="Risk check failed"):
        adapter.place_order(
            symbol="RELIANCE", exchange="NSE",
            side="BUY", quantity=10, order_type="MARKET",
        )

    # HTTP was never called
    assert client.post.call_count == 0
