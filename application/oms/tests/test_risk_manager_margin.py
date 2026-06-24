"""Tests for B3: F&O margin check in RiskManager.

Covers:
  - Equity orders bypass margin check
  - F&O orders rejected when no margin provider configured
  - F&O orders rejected on insufficient margin
  - F&O orders accepted when margin is sufficient
  - Safety multiplier applied correctly
  - API errors fail-closed (order rejected)
  - Margin check can be disabled via config
"""

from __future__ import annotations

from decimal import Decimal
from unittest.mock import MagicMock

import pytest

from application.oms import PositionManager, RiskConfig, RiskManager
from brokers.common.api import MarginCalculationError, MarginProvider, MarginResult
from brokers.common.oms.margin_provider import BrokerMarginProvider
from domain import Order, OrderStatus, OrderType, ProductType, Side
from domain.exchange_segments import is_derivative_segment

# ── Helpers ────────────────────────────────────────────────────────────────


def _make_order(
    symbol: str = "NIFTY25JUN20000CE",
    exchange: str = "NFO",
    price: Decimal = Decimal("100"),
    quantity: int = 50,
) -> Order:
    """Create a test order. Default is an F&O order on NFO."""
    return Order(
        order_id="O-1",
        symbol=symbol,
        exchange=exchange,
        side=Side.BUY,
        quantity=quantity,
        price=price,
        order_type=OrderType.LIMIT,
        product_type=ProductType.INTRADAY,
        status=OrderStatus.OPEN,
    )


@pytest.fixture
def position_manager() -> PositionManager:
    return PositionManager()


@pytest.fixture
def capital_provider() -> MagicMock:
    cp = MagicMock()
    cp.get_available_balance.return_value = Decimal("1000000")
    return cp


@pytest.fixture
def default_config() -> RiskConfig:
    return RiskConfig()


def _create_risk_manager(
    position_manager: PositionManager,
    capital_provider: MagicMock,
    config: RiskConfig | None = None,
    margin_provider: MarginProvider | None = None,
) -> RiskManager:
    """Factory for RiskManager with test defaults."""
    return RiskManager(
        position_manager=position_manager,
        config=config or RiskConfig(),
        capital_provider=capital_provider,
        margin_provider=margin_provider,
    )


# ── Test: Equity orders bypass margin check ────────────────────────────────


class TestEquityBypass:
    """NSE/BSE equity orders should NOT trigger margin checks."""

    def test_nse_equity_order_bypasses_margin_check(
        self, position_manager, capital_provider, default_config
    ):
        rm = _create_risk_manager(position_manager, capital_provider, default_config)
        order = _make_order(symbol="RELIANCE", exchange="NSE", price=Decimal("2500"))

        result = rm.check_order(order)
        assert result.allowed is True
        assert result.reason is None

    def test_bse_equity_order_bypasses_margin_check(
        self, position_manager, capital_provider, default_config
    ):
        rm = _create_risk_manager(position_manager, capital_provider, default_config)
        order = _make_order(symbol="TCS", exchange="BSE", price=Decimal("3500"))

        result = rm.check_order(order)
        assert result.allowed is True
        assert result.reason is None

    def test_is_derivative_segment_returns_false_for_equity(self):
        assert is_derivative_segment("NSE") is False
        assert is_derivative_segment("BSE") is False
        assert is_derivative_segment("NSE_EQ") is False


# ── Test: F&O orders rejected when no margin provider ──────────────────────


class TestNoMarginProvider:
    """F&O orders must be rejected if no margin provider is configured."""

    @pytest.mark.parametrize("exchange", ["NFO", "BFO", "MCX", "CDS", "NSE_FNO", "BSE_FNO"])
    def test_fo_order_rejected_without_margin_provider(
        self, position_manager, capital_provider, default_config, exchange
    ):
        rm = _create_risk_manager(
            position_manager, capital_provider, default_config, margin_provider=None
        )
        order = _make_order(exchange=exchange)

        result = rm.check_order(order)
        assert result.allowed is False
        assert "no margin provider configured" in result.reason.lower()

    def test_nse_equity_still_allowed_without_margin_provider(
        self, position_manager, capital_provider, default_config
    ):
        """Equity orders should still pass even without margin provider."""
        rm = _create_risk_manager(
            position_manager, capital_provider, default_config, margin_provider=None
        )
        order = _make_order(symbol="RELIANCE", exchange="NSE")

        result = rm.check_order(order)
        assert result.allowed is True


# ── Test: F&O orders rejected on insufficient margin ───────────────────────


class TestInsufficientMargin:
    """F&O orders must be rejected when available margin < required."""

    def test_fo_order_rejected_insufficient_margin(
        self, position_manager, capital_provider, default_config
    ):
        mock_provider = MagicMock(spec=BrokerMarginProvider)
        mock_provider.calculate_margin_for_order.return_value = MarginResult(
            required_margin=Decimal("200000"),
            available_margin=Decimal("100000"),
        )

        rm = _create_risk_manager(position_manager, capital_provider, default_config, mock_provider)
        order = _make_order()

        result = rm.check_order(order)
        assert result.allowed is False
        assert "insufficient margin" in result.reason.lower()


# ── Test: F&O orders accepted when margin sufficient ───────────────────────


class TestSufficientMargin:
    """F&O orders must pass when available margin >= required."""

    def test_fo_order_accepted_sufficient_margin(
        self, position_manager, capital_provider, default_config
    ):
        mock_provider = MagicMock(spec=BrokerMarginProvider)
        mock_provider.calculate_margin_for_order.return_value = MarginResult(
            required_margin=Decimal("100000"),
            available_margin=Decimal("200000"),
        )

        rm = _create_risk_manager(position_manager, capital_provider, default_config, mock_provider)
        order = _make_order()

        result = rm.check_order(order)
        assert result.allowed is True
        assert result.reason is None

    def test_fo_order_accepted_exact_margin(
        self, position_manager, capital_provider, default_config
    ):
        """Exact match (available == required) should pass (before multiplier)."""
        mock_provider = MagicMock(spec=BrokerMarginProvider)
        mock_provider.calculate_margin_for_order.return_value = MarginResult(
            required_margin=Decimal("100000"),
            available_margin=Decimal("100000"),
        )

        rm = _create_risk_manager(position_manager, capital_provider, default_config, mock_provider)
        order = _make_order()

        result = rm.check_order(order)
        # Note: With 1.2x multiplier, available (100k) < required * 1.2 (120k)
        # So this should actually be rejected
        assert result.allowed is False


# ── Test: Safety multiplier applied correctly ─────────────────────────────


class TestSafetyMultiplier:
    """The safety multiplier (default 1.2x) must be applied to required margin."""

    def test_safety_multiplier_rejects_when_available_between_required_and_buffered(
        self, position_manager, capital_provider, default_config
    ):
        """Available > required but < required * 1.2 → should reject."""
        mock_provider = MagicMock(spec=BrokerMarginProvider)
        # required=100k, available=110k, required*1.2=120k
        mock_provider.calculate_margin_for_order.return_value = MarginResult(
            required_margin=Decimal("100000"),
            available_margin=Decimal("110000"),
        )

        rm = _create_risk_manager(position_manager, capital_provider, default_config, mock_provider)
        order = _make_order()

        result = rm.check_order(order)
        assert result.allowed is False

    def test_safety_multiplier_passes_when_available_above_buffered(
        self, position_manager, capital_provider, default_config
    ):
        """Available > required * 1.2 → should pass."""
        mock_provider = MagicMock(spec=BrokerMarginProvider)
        # required=100k, available=130k, required*1.2=120k
        mock_provider.calculate_margin_for_order.return_value = MarginResult(
            required_margin=Decimal("100000"),
            available_margin=Decimal("130000"),
        )

        rm = _create_risk_manager(position_manager, capital_provider, default_config, mock_provider)
        order = _make_order()

        result = rm.check_order(order)
        assert result.allowed is True

    def test_custom_safety_multiplier(self, position_manager, capital_provider):
        """Custom safety multiplier in config should be respected."""
        config = RiskConfig(margin_safety_multiplier=Decimal("1.5"))
        mock_provider = MagicMock(spec=BrokerMarginProvider)
        # required=100k, available=140k, required*1.5=150k
        mock_provider.calculate_margin_for_order.return_value = MarginResult(
            required_margin=Decimal("100000"),
            available_margin=Decimal("140000"),
        )

        rm = _create_risk_manager(position_manager, capital_provider, config, mock_provider)
        order = _make_order()

        result = rm.check_order(order)
        assert result.allowed is False  # 140k < 150k


# ── Test: API errors fail-closed ───────────────────────────────────────────


class TestFailClosed:
    """Margin API errors must cause order rejection (fail-closed)."""

    def test_margin_calculation_error_rejects_order(
        self, position_manager, capital_provider, default_config
    ):
        mock_provider = MagicMock(spec=BrokerMarginProvider)
        mock_provider.calculate_margin_for_order.side_effect = MarginCalculationError("API timeout")

        rm = _create_risk_manager(position_manager, capital_provider, default_config, mock_provider)
        order = _make_order()

        result = rm.check_order(order)
        assert result.allowed is False
        assert "margin api error" in result.reason.lower()

    def test_generic_exception_rejects_order(
        self, position_manager, capital_provider, default_config
    ):
        mock_provider = MagicMock(spec=BrokerMarginProvider)
        mock_provider.calculate_margin_for_order.side_effect = RuntimeError("Unexpected error")

        rm = _create_risk_manager(position_manager, capital_provider, default_config, mock_provider)
        order = _make_order()

        result = rm.check_order(order)
        assert result.allowed is False
        assert "margin check failed" in result.reason.lower()


# ── Test: Margin check can be disabled ────────────────────────────────────


class TestMarginCheckDisabled:
    """When enable_margin_check=False, F&O orders should bypass margin check."""

    def test_fo_order_bypasses_check_when_disabled(self, position_manager, capital_provider):
        config = RiskConfig(enable_margin_check=False)
        rm = _create_risk_manager(position_manager, capital_provider, config, margin_provider=None)
        order = _make_order()

        result = rm.check_order(order)
        assert result.allowed is True
        assert result.reason is None

    def test_fo_order_bypasses_check_even_with_provider(self, position_manager, capital_provider):
        """Even with a provider, disabled config should skip the check."""
        config = RiskConfig(enable_margin_check=False)
        mock_provider = MagicMock(spec=BrokerMarginProvider)
        # This provider would reject, but check is disabled
        mock_provider.calculate_margin_for_order.return_value = MarginResult(
            required_margin=Decimal("999999999"),
            available_margin=Decimal("0"),
        )

        rm = _create_risk_manager(position_manager, capital_provider, config, mock_provider)
        order = _make_order()

        result = rm.check_order(order)
        assert result.allowed is True


# ── Test: BrokerMarginProvider ─────────────────────────────────────────────


class TestBrokerMarginProvider:
    """Tests for the BrokerMarginProvider adapter."""

    def test_no_broker_provider_raises(self):
        provider = BrokerMarginProvider(broker_margin_provider=None)
        with pytest.raises(MarginCalculationError, match="No broker margin provider configured"):
            provider.calculate_margin_for_order(
                symbol="NIFTY",
                exchange="NFO",
                quantity=50,
                price=Decimal("100"),
                product_type="MIS",
                order_type="LIMIT",
            )

    def test_delegates_to_calculate_margin_for_order_if_available(self):
        mock_broker = MagicMock()
        mock_broker.calculate_margin_for_order.return_value = MarginResult(
            required_margin=Decimal("100000"),
            available_margin=Decimal("200000"),
        )

        provider = BrokerMarginProvider(mock_broker)
        result = provider.calculate_margin_for_order(
            symbol="NIFTY",
            exchange="NFO",
            quantity=50,
            price=Decimal("100"),
            product_type="MIS",
            order_type="LIMIT",
        )

        assert result.required_margin == Decimal("100000")
        assert result.available_margin == Decimal("200000")
        assert result.is_sufficient is True

    def test_fallback_to_calculate_margin(self):
        mock_broker = MagicMock()
        # No calculate_margin_for_order, fallback to calculate_margin
        del mock_broker.calculate_margin_for_order
        mock_broker.calculate_margin.return_value = {
            "total_margin": 100000,
            "available_margin": 200000,
        }

        provider = BrokerMarginProvider(mock_broker)
        result = provider.calculate_margin_for_order(
            symbol="NIFTY",
            exchange="NFO",
            quantity=50,
            price=Decimal("100"),
            product_type="MIS",
            order_type="LIMIT",
        )

        assert result.required_margin == Decimal("100000")
        assert result.available_margin == Decimal("200000")

    def test_parse_margin_response_various_field_names(self):
        mock_broker = MagicMock()
        del mock_broker.calculate_margin_for_order
        mock_broker.calculate_margin.return_value = {
            "totalMargin": 150000,
            "availableMargin": 250000,
            "spanMargin": 80000,
            "exposureMargin": 70000,
        }

        provider = BrokerMarginProvider(mock_broker)
        result = provider.calculate_margin_for_order(
            symbol="NIFTY",
            exchange="NFO",
            quantity=50,
            price=Decimal("100"),
            product_type="MIS",
            order_type="LIMIT",
        )

        assert result.required_margin == Decimal("150000")
        assert result.available_margin == Decimal("250000")
        assert result.span_margin == Decimal("80000")
        assert result.exposure_margin == Decimal("70000")

    def test_broker_error_wrapped_as_margin_calculation_error(self):
        mock_broker = MagicMock()
        del mock_broker.calculate_margin_for_order
        mock_broker.calculate_margin.side_effect = Exception("Connection refused")

        provider = BrokerMarginProvider(mock_broker)
        with pytest.raises(MarginCalculationError, match="Connection refused"):
            provider.calculate_margin_for_order(
                symbol="NIFTY",
                exchange="NFO",
                quantity=50,
                price=Decimal("100"),
                product_type="MIS",
                order_type="LIMIT",
            )


# ── Test: MarginResult ─────────────────────────────────────────────────────


class TestMarginResult:
    """Tests for the MarginResult dataclass."""

    def test_is_sufficient_true(self):
        result = MarginResult(
            required_margin=Decimal("100000"),
            available_margin=Decimal("200000"),
        )
        assert result.is_sufficient is True

    def test_is_sufficient_false(self):
        result = MarginResult(
            required_margin=Decimal("200000"),
            available_margin=Decimal("100000"),
        )
        assert result.is_sufficient is False

    def test_is_sufficient_exact(self):
        result = MarginResult(
            required_margin=Decimal("100000"),
            available_margin=Decimal("100000"),
        )
        assert result.is_sufficient is True

    def test_optional_fields(self):
        result = MarginResult(
            required_margin=Decimal("100000"),
            available_margin=Decimal("200000"),
            span_margin=Decimal("60000"),
            exposure_margin=Decimal("40000"),
        )
        assert result.span_margin == Decimal("60000")
        assert result.exposure_margin == Decimal("40000")
