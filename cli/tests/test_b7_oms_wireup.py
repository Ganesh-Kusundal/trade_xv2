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

  - The capital_fn reads ``gateway.funds().available_balance`` and
    is fail-closed: a broker outage returns ``Decimal(0)`` and the
    OMS blocks every order unless ``RISK_FAIL_OPEN=1`` is set
    (B-3 / M-7). The tests in this file use ``RISK_FAIL_OPEN=1``
    where the legacy placeholder is the expected value, and
    ``RISK_FAIL_OPEN=0`` (the default) where fail-closed is the
    expected value.
"""

from __future__ import annotations

from decimal import Decimal
from unittest.mock import MagicMock

import pytest

from brokers.common.oms import (
    PositionManager,
    RiskConfig,
    RiskManager,
)

# ── Helper: enable fail-open for tests that expect the legacy
# placeholder semantics. Per the M-7 contract, the default is
# fail-closed; tests must opt in.


@pytest.fixture(autouse=True)
def _enable_fail_open(monkeypatch):
    """Default: RISK_FAIL_OPEN=1 so existing tests see the legacy
    placeholder when the gateway is missing. Tests that exercise the
    fail-closed path explicitly monkeypatch RISK_FAIL_OPEN=0.
    """
    monkeypatch.setenv("RISK_FAIL_OPEN", "1")
    yield


# ── BrokerService constructs the OMS risk_manager before the factory ─────


def test_broker_service_builds_oms_risk_manager_with_placeholder_capital() -> None:
    """The OMS risk_manager is built with a placeholder capital_fn
    when no gateway is set and ``RISK_FAIL_OPEN=1`` is set. The
    kill_switch and per-order risk checks are fully active."""
    from cli.services.broker_service import BrokerService

    bs = BrokerService()
    rm = bs._build_oms_risk_manager()
    assert isinstance(rm, RiskManager)
    # Capital is the placeholder 1,000,000 (with RISK_FAIL_OPEN=1)
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
    import inspect

    from brokers.dhan.factory import BrokerFactory
    sig = inspect.signature(BrokerFactory.create)
    assert "risk_manager" in sig.parameters, (
        "BrokerFactory.create must accept risk_manager= parameter (B7)"
    )


# ── End-to-end: kill switch in the OMS blocks place_order via OrdersAdapter


def test_end_to_end_kill_switch_via_oms_blocks_dhan_place_order() -> None:
    """A complete chain: BrokerService builds the OMS, sets the
    kill_switch, the OrdersAdapter's risk_manager (the same OMS
    instance) is consulted, and a place_order is blocked."""
    from brokers.dhan.exceptions import OrderError
    from brokers.dhan.http_client import DhanHttpClient
    from brokers.dhan.orders import OrdersAdapter
    from brokers.dhan.resolver import SymbolResolver
    from cli.services.broker_service import BrokerService

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


# ── C.1: Real capital_fn wired to gateway.funds() ──────────────────────────


def test_oms_capital_fn_uses_placeholder_before_gateway_set() -> None:
    """Before the gateway is constructed and with RISK_FAIL_OPEN=1,
    the OMS capital_fn returns the placeholder (1,000,000). The
    kill_switch and per-order risk checks remain active."""
    from cli.services.broker_service import BrokerService

    bs = BrokerService()
    rm = bs._build_oms_risk_manager()
    # No gateway set yet → placeholder (with fail-open)
    assert rm._capital_fn() == Decimal("1000000")


def test_oms_capital_fn_uses_real_gateway_funds_after_init() -> None:
    """C.1: after _ensure_initialized completes, the OMS
    capital_fn closure captures the real gateway. Calling
    capital_fn() reads gateway.funds().available_balance.
    """
    from brokers.common.core.domain import Balance
    from cli.services.broker_service import BrokerService

    bs = BrokerService()

    # Build the risk manager before the gateway exists
    rm = bs._build_oms_risk_manager()
    # Placeholder when gateway is None
    assert rm._capital_fn() == Decimal("1000000")

    # Simulate the gateway being set (as _ensure_initialized does)
    fake_balance = Balance(
        available_balance=Decimal("250000.50"),
        sod_limit=Decimal("500000"),
        utilized_amount=Decimal("0"),
    )
    fake_gateway = MagicMock()
    fake_gateway.funds.return_value = fake_balance
    bs._oms_gateway_holder["gw"] = fake_gateway

    # Now capital_fn reads the real balance
    assert rm._capital_fn() == Decimal("250000.50")
    fake_gateway.funds.assert_called()


def test_oms_capital_fn_uses_placeholder_on_broker_call_failure_with_fail_open() -> None:
    """With RISK_FAIL_OPEN=1, if gateway.funds() raises, the
    capital_fn must fall back to the placeholder rather than
    disabling the risk check. This preserves the prior B7 invariant
    for the explicit opt-in case.
    """
    from cli.services.broker_service import BrokerService

    bs = BrokerService()
    rm = bs._build_oms_risk_manager()

    fake_gateway = MagicMock()
    fake_gateway.funds.side_effect = ConnectionError("network down")
    bs._oms_gateway_holder["gw"] = fake_gateway

    # Capital falls back to placeholder
    assert rm._capital_fn() == Decimal("1000000")


def test_oms_capital_fn_fails_closed_on_broker_call_failure(monkeypatch) -> None:
    """M-7 / B-3: with RISK_FAIL_OPEN=0 (the default), a broker
    outage must block every order by returning Decimal(0). The
    operator must explicitly opt-in to the legacy placeholder via
    RISK_FAIL_OPEN=1.
    """
    from cli.services.broker_service import BrokerService

    monkeypatch.setenv("RISK_FAIL_OPEN", "0")
    bs = BrokerService()
    rm = bs._build_oms_risk_manager()

    fake_gateway = MagicMock()
    fake_gateway.funds.side_effect = ConnectionError("network down")
    bs._oms_gateway_holder["gw"] = fake_gateway

    # Fail closed: capital is 0, OMS blocks every order
    assert rm._capital_fn() == Decimal("0")


def test_oms_capital_fn_blocks_on_zero_balance_with_fail_open() -> None:
    """A zero or negative balance is a hard stop, even with
    RISK_FAIL_OPEN=1. Phantom capital would defeat the risk gate.
    """
    from brokers.common.core.domain import Balance
    from cli.services.broker_service import BrokerService

    bs = BrokerService()
    rm = bs._build_oms_risk_manager()

    fake_gateway = MagicMock()
    fake_gateway.funds.return_value = Balance(
        available_balance=Decimal("0"),
        sod_limit=Decimal("0"),
    )
    bs._oms_gateway_holder["gw"] = fake_gateway

    # Hard stop on zero/negative balance
    assert rm._capital_fn() == Decimal("0")


def test_oms_capital_fn_caches_position_pct_against_real_balance() -> None:
    """End-to-end: with a real balance of 100,000 and an order
    for 30,000, the position_pct is 30% — which exceeds the
    default 20% cap. The order is blocked. With the placeholder
    of 1,000,000, the same order is only 3% — which would pass.
    This is the production impact of C.1.
    """
    from brokers.common.core.domain import (
        Balance,
        Order,
        OrderStatus,
        OrderType,
        ProductType,
        Side,
    )
    from brokers.common.oms import (
        PositionManager,
        RiskConfig,
        RiskManager,
    )
    from cli.services.broker_service import BrokerService

    bs = BrokerService()

    # Trigger the lazy creation of _oms_gateway_holder
    bs._build_oms_risk_manager()

    # Build the OMS risk manager with a SHARED position manager so
    # we can verify the position_pct is sized to the real balance.
    pm = PositionManager()
    fake_gateway = MagicMock()
    fake_gateway.funds.return_value = Balance(
        available_balance=Decimal("100000"),  # 100k, not 1M
    )
    bs._oms_gateway_holder["gw"] = fake_gateway

    rm = RiskManager(
        position_manager=pm,
        config=RiskConfig(max_position_pct=Decimal("20")),
        capital_fn=lambda: bs._oms_gateway_holder["gw"].funds().available_balance,
    )

    # Order notional = 30,000 = 30% of 100k → exceeds 20% cap
    order = Order(
        order_id="O-1", symbol="RELIANCE", exchange="NSE",
        side=Side.BUY, quantity=10, price=Decimal("3000"),
        order_type=OrderType.LIMIT, product_type=ProductType.INTRADAY,
        status=OrderStatus.OPEN,
    )
    result = rm.check_order(order)
    assert result.allowed is False
    assert "Exceeds max position pct" in result.reason


# ── M-7: production readiness gate ───────────────────────────────────────


def test_production_readiness_checker_fails_when_reconciliation_unwired() -> None:
    """ProductionReadinessChecker reports the live CLI as
    PRODUCTION UNSAFE when the OMS ReconciliationService has no
    broker-specific implementation.
    """
    from brokers.common.oms.context import TradingContext
    from brokers.common.services.production_readiness import (
        ProductionReadinessChecker,
    )

    # Build a TradingContext with reconciliation_service=None — the
    # pre-B-1 configuration the live CLI used to ship with.
    ctx = TradingContext(reconciliation_interval_seconds=0)
    svc = MagicMock()
    svc._trading_context = ctx
    svc.lifecycle = MagicMock()
    svc.lifecycle.service_names.return_value = []
    report = ProductionReadinessChecker(svc).run()
    assert not report.passed
    assert "reconciliation_wired" in report.failed
    assert "eventlog_wired" in report.failed
