"""Unit tests for ModelMapper — bidirectional model translation."""

from decimal import Decimal

from brokers.common.core import domain, models
from brokers.common.core.enums import (
    ExchangeSegment,
    TransactionType,
)
from brokers.common.core.enums import (
    OrderStatus as ModelOrderStatus,
)
from brokers.common.core.enums import (
    OrderType as ModelOrderType,
)
from brokers.common.core.enums import (
    ProductType as ModelProductType,
)
from brokers.common.core.enums import (
    Validity as ModelValidity,
)
from brokers.common.core.mappers import (
    fund_limits_to_domain,
    holding_list_to_domain,
    holding_to_domain,
    order_list_to_domain,
    order_response_to_domain,
    order_to_domain,
    position_list_to_domain,
    position_to_domain,
    trade_list_to_domain,
    trade_to_domain,
)


class TestOrderMapper:
    def test_buy_order(self):
        m = models.Order(
            order_id="ORD-1",
            symbol="RELIANCE",
            exchange_segment=ExchangeSegment.NSE,
            transaction_type=TransactionType.BUY,
            quantity=10,
            price=Decimal("2500"),
            order_type=ModelOrderType.LIMIT,
            product_type=ModelProductType.CNC,
            validity=ModelValidity.DAY,
            status=ModelOrderStatus.OPEN,
            filled_quantity=0,
            average_price=Decimal("0"),
        )
        d = order_to_domain(m)
        assert isinstance(d, domain.Order)
        assert d.order_id == "ORD-1"
        assert d.symbol == "RELIANCE"
        assert d.exchange == "NSE"
        assert d.side == domain.Side.BUY
        assert d.quantity == 10
        assert d.price == Decimal("2500")
        assert d.order_type == domain.OrderType.LIMIT
        assert d.product_type == domain.ProductType.CNC
        assert d.status == domain.OrderStatus.OPEN
        assert d.filled_quantity == 0

    def test_sell_order(self):
        m = models.Order(
            order_id="ORD-2",
            transaction_type=TransactionType.SELL,
            exchange_segment=ExchangeSegment.NSE_FNO,
        )
        d = order_to_domain(m)
        assert d.side == domain.Side.SELL
        assert d.exchange == "NFO"

    def test_executed_maps_to_filled(self):
        m = models.Order(order_id="X", status=ModelOrderStatus.EXECUTED)
        d = order_to_domain(m)
        assert d.status == domain.OrderStatus.FILLED

    def test_null_trigger_price(self):
        m = models.Order(order_id="X", trigger_price=None)
        d = order_to_domain(m)
        assert d.trigger_price == Decimal("0")

    def test_minimal_order_defaults(self):
        m = models.Order(order_id="MIN")
        d = order_to_domain(m)
        assert d.price == Decimal("0")
        assert d.reject_reason == ""
        assert d.correlation_id is None

    def test_order_list_batch(self):
        items = [
            models.Order(order_id="A", transaction_type=TransactionType.BUY),
            models.Order(order_id="B", transaction_type=TransactionType.SELL),
        ]
        results = order_list_to_domain(items)
        assert len(results) == 2
        assert results[0].side == domain.Side.BUY
        assert results[1].side == domain.Side.SELL


class TestPositionMapper:
    def test_long_position(self):
        m = models.Position(
            symbol="RELIANCE",
            exchange_segment=ExchangeSegment.NSE,
            quantity=10,
            net_quantity=10,
            buy_average_price=Decimal("2500"),
            last_price=Decimal("2550"),
            unrealized_pnl=Decimal("500"),
            realized_pnl=Decimal("0"),
            product_type=ModelProductType.INTRADAY,
        )
        d = position_to_domain(m)
        assert isinstance(d, domain.Position)
        assert d.symbol == "RELIANCE"
        assert d.exchange == "NSE"
        assert d.quantity == 10
        assert d.avg_price == Decimal("2500")
        assert d.ltp == Decimal("2550")
        assert d.unrealized_pnl == Decimal("500")

    def test_fno_position(self):
        m = models.Position(
            symbol="NIFTY25JUN19000CE",
            exchange_segment=ExchangeSegment.NSE_FNO,
            net_quantity=-75,
            product_type=ModelProductType.MARGIN,
        )
        d = position_to_domain(m)
        assert d.exchange == "NFO"
        assert d.quantity == -75

    def test_position_list_batch(self):
        items = [
            models.Position(symbol="A", exchange_segment=ExchangeSegment.NSE),
            models.Position(symbol="B", exchange_segment=ExchangeSegment.BSE),
        ]
        results = position_list_to_domain(items)
        assert len(results) == 2
        assert results[0].exchange == "NSE"
        assert results[1].exchange == "BSE"


class TestHoldingMapper:
    def test_holding(self):
        m = models.Holding(
            symbol="INFY",
            exchange_segment=ExchangeSegment.NSE,
            quantity=20,
            available_quantity=20,
            cost_price=Decimal("1420"),
            last_price=Decimal("1435"),
            pnl_value=Decimal("300"),
        )
        d = holding_to_domain(m)
        assert isinstance(d, domain.Holding)
        assert d.symbol == "INFY"
        assert d.exchange == "NSE"
        assert d.quantity == 20
        assert d.avg_price == Decimal("1420")
        assert d.ltp == Decimal("1435")
        assert d.pnl == Decimal("300")

    def test_holding_string_segment(self):
        m = models.Holding(symbol="X", exchange_segment="NSE_EQ")
        d = holding_to_domain(m)
        assert d.exchange == "NSE"

    def test_holding_list_batch(self):
        items = [models.Holding(symbol="A"), models.Holding(symbol="B")]
        results = holding_list_to_domain(items)
        assert len(results) == 2


class TestTradeMapper:
    def test_buy_trade(self):
        m = models.Trade(
            trade_id="TRD-1",
            order_id="ORD-1",
            symbol="RELIANCE",
            exchange_segment=ExchangeSegment.NSE,
            transaction_type=TransactionType.BUY,
            quantity=10,
            price=Decimal("2500"),
            trade_value=Decimal("25000"),
            product_type=ModelProductType.CNC,
        )
        d = trade_to_domain(m)
        assert isinstance(d, domain.Trade)
        assert d.side == domain.Side.BUY
        assert d.trade_value == Decimal("25000")

    def test_trade_value_calculated_when_zero(self):
        m = models.Trade(
            trade_id="TRD-2",
            order_id="ORD-2",
            quantity=5,
            price=Decimal("100"),
            trade_value=Decimal("0"),
            transaction_type=TransactionType.SELL,
        )
        d = trade_to_domain(m)
        assert d.trade_value == Decimal("500")

    def test_trade_list_batch(self):
        items = [
            models.Trade(trade_id="T1", order_id="O1", transaction_type=TransactionType.BUY),
            models.Trade(trade_id="T2", order_id="O2", transaction_type=TransactionType.SELL),
        ]
        results = trade_list_to_domain(items)
        assert len(results) == 2


class TestFundLimitsMapper:
    def test_full_funds(self):
        m = models.FundLimits(
            available_balance=Decimal("452300.50"),
            used_margin=Decimal("47700"),
            total_margin=Decimal("500000"),
            collateral=Decimal("100000"),
            m2m_realized=Decimal("5000"),
            m2m_unrealized=Decimal("-2000"),
        )
        d = fund_limits_to_domain(m)
        assert isinstance(d, domain.FundLimits)
        assert d.available_balance == Decimal("452300.50")
        assert d.used_margin == Decimal("47700")
        assert d.total_margin == Decimal("500000")

    def test_zero_funds(self):
        m = models.FundLimits()
        d = fund_limits_to_domain(m)
        assert d.available_balance == Decimal("0")


class TestOrderResponseMapper:
    def test_success_response(self):
        m = models.OrderResponse.create_success("ORD-123", "Order placed")
        d = order_response_to_domain(m)
        assert isinstance(d, domain.OrderResponse)
        assert d.success is True
        assert d.order_id == "ORD-123"

    def test_failure_response(self):
        m = models.OrderResponse.create_failure("Insufficient funds")
        d = order_response_to_domain(m)
        assert d.success is False
        assert d.order_id == ""
        assert "Insufficient" in d.message

    def test_with_order_status(self):
        m = models.OrderResponse(
            success=True,
            order_id="X",
            order_status=ModelOrderStatus.EXECUTED,
        )
        d = order_response_to_domain(m)
        assert d.status == domain.OrderStatus.FILLED
