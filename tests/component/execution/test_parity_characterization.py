"""REF-007: Execution parity characterization tests.

Verifies that the same OmsOrderCommand routed through Paper and
Replay execution adapters produces structurally identical OrderResult
objects. Live mode is tested separately via OrderManager directly.
"""

from __future__ import annotations
from tests.conftest import build_test_trading_context

from decimal import Decimal

import pytest

from application.execution.oms_backtest_adapter import (
    SimulatedOMSAdapter,
    create_execution_adapter,
)
from application.oms.context import TradingContext
from application.oms.order_manager import OmsOrderCommand, OrderResult
from application.oms._internal.risk_manager import RiskConfig
from domain import OrderType, ProductType, Side

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def trading_context() -> TradingContext:
    """Minimal TradingContext with permissive risk for parity testing."""
    return build_test_trading_context(
        capital_fn=lambda: Decimal("1000000"),
        risk_config=RiskConfig(
            max_position_pct=Decimal("100"),
            max_gross_exposure_pct=Decimal("100"),
            max_daily_loss_pct=Decimal("100"),
        ),
    )


@pytest.fixture
def base_command() -> OmsOrderCommand:
    """Canonical order command used across all adapters."""
    return OmsOrderCommand(
        symbol="RELIANCE",
        exchange="NSE",
        side=Side.BUY,
        quantity=10,
        price=Decimal("2500"),
        order_type=OrderType.MARKET,
        product_type=ProductType.INTRADAY,
        correlation_id="parity-test:001",
    )


def _place_via_adapter(adapter, command: OmsOrderCommand) -> OrderResult:
    """Helper to place an order through any adapter."""
    return adapter.place_order(command)


# ---------------------------------------------------------------------------
# Parity tests — structure
# ---------------------------------------------------------------------------


class TestOrderResultParity:
    """All adapters must return OrderResult with the same structural shape."""

    def test_paper_returns_order_result(self, trading_context, base_command):
        adapter = create_execution_adapter("paper", trading_context)
        result = _place_via_adapter(adapter, base_command)
        assert isinstance(result, OrderResult)

    def test_replay_returns_order_result(self, trading_context, base_command):
        adapter = create_execution_adapter("replay", trading_context)
        result = _place_via_adapter(adapter, base_command)
        assert isinstance(result, OrderResult)

    def test_all_adapters_set_success(self, trading_context, base_command):
        """Both simulated adapters should succeed with a permissive risk config."""
        for mode in ("paper", "replay"):
            adapter = create_execution_adapter(mode, trading_context)
            result = _place_via_adapter(adapter, base_command)
            assert result.success is True, f"{mode} adapter failed: {result.error}"

    def test_all_adapters_return_order(self, trading_context, base_command):
        """All adapters must populate result.order on success."""
        for mode in ("paper", "replay"):
            adapter = create_execution_adapter(mode, trading_context)
            result = _place_via_adapter(adapter, base_command)
            assert result.order is not None, f"{mode} adapter returned no order"

    def test_all_adapters_have_order_id(self, trading_context, base_command):
        """All adapters must assign an order_id."""
        for mode in ("paper", "replay"):
            adapter = create_execution_adapter(mode, trading_context)
            result = _place_via_adapter(adapter, base_command)
            assert result.order is not None
            assert len(result.order.order_id) > 0

    def test_all_adapters_preserve_symbol(self, trading_context, base_command):
        """Order symbol must match the command symbol."""
        for mode in ("paper", "replay"):
            adapter = create_execution_adapter(mode, trading_context)
            result = _place_via_adapter(adapter, base_command)
            assert result.order is not None
            assert result.order.symbol == base_command.symbol

    def test_all_adapters_preserve_side(self, trading_context, base_command):
        """Order side must match the command side."""
        for mode in ("paper", "replay"):
            adapter = create_execution_adapter(mode, trading_context)
            result = _place_via_adapter(adapter, base_command)
            assert result.order is not None
            assert result.order.side == base_command.side

    def test_all_adapters_preserve_quantity(self, trading_context, base_command):
        """Order quantity must match the command quantity."""
        for mode in ("paper", "replay"):
            adapter = create_execution_adapter(mode, trading_context)
            result = _place_via_adapter(adapter, base_command)
            assert result.order is not None
            assert result.order.quantity == base_command.quantity

    def test_all_adapters_preserve_exchange(self, trading_context, base_command):
        """Order exchange must match the command exchange."""
        for mode in ("paper", "replay"):
            adapter = create_execution_adapter(mode, trading_context)
            result = _place_via_adapter(adapter, base_command)
            assert result.order is not None
            assert result.order.exchange == base_command.exchange


# ---------------------------------------------------------------------------
# Parity tests — sell side
# ---------------------------------------------------------------------------


class TestSellSideParity:
    """Sell orders must also pass through all adapters uniformly."""

    @pytest.fixture
    def sell_command(self) -> OmsOrderCommand:
        return OmsOrderCommand(
            symbol="TCS",
            exchange="NSE",
            side=Side.SELL,
            quantity=5,
            price=Decimal("3500"),
            order_type=OrderType.MARKET,
            product_type=ProductType.INTRADAY,
            correlation_id="parity-test:sell-001",
        )

    def test_all_adapters_handle_sell(self, trading_context, sell_command):
        for mode in ("paper", "replay"):
            adapter = create_execution_adapter(mode, trading_context)
            result = _place_via_adapter(adapter, sell_command)
            assert result.success is True, f"{mode} sell failed: {result.error}"
            assert result.order is not None
            assert result.order.side == Side.SELL


# ---------------------------------------------------------------------------
# Parity tests — factory
# ---------------------------------------------------------------------------


class TestAdapterFactory:
    """create_execution_adapter must return the correct adapter type."""

    def test_paper_adapter_type(self, trading_context):
        adapter = create_execution_adapter("paper", trading_context)
        assert isinstance(adapter, SimulatedOMSAdapter)

    def test_replay_adapter_type(self, trading_context):
        adapter = create_execution_adapter("replay", trading_context)
        assert isinstance(adapter, SimulatedOMSAdapter)

    def test_backtest_adapter_type(self, trading_context):
        adapter = create_execution_adapter("backtest", trading_context)
        assert isinstance(adapter, SimulatedOMSAdapter)

    def test_unknown_mode_raises(self, trading_context):
        with pytest.raises(ValueError, match="Unknown execution target"):
            create_execution_adapter("turbo", trading_context)

    def test_live_mode_raises(self, trading_context):
        with pytest.raises(ValueError, match="Live mode"):
            create_execution_adapter("live", trading_context)
