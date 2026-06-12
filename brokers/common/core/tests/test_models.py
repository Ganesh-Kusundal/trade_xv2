"""TDD tests for broker.core.models."""

from decimal import Decimal

from brokers.common.core.enums import (
    ExchangeSegment,
    OrderStatus,
    OrderType,
    TransactionType,
)
from brokers.common.core.models import (
    FundLimits,
    HistoricalCandle,
    Holding,
    OptionContract,
    Order,
    OrderRequest,
    OrderResponse,
    Position,
    Quote,
    Trade,
)


class TestOrderRequest:
    def test_basic_buy(self):
        req = OrderRequest(
            security_id="2885",
            exchange_segment=ExchangeSegment.NSE,
            transaction_type=TransactionType.BUY,
            quantity=10,
            price=Decimal("2450"),
            order_type=OrderType.LIMIT,
        )
        assert req.security_id == "2885"
        assert req.quantity == 10
        assert req.estimated_value() == Decimal("24500")

    def test_market_order_no_price(self):
        req = OrderRequest(
            security_id="2885",
            exchange_segment=ExchangeSegment.NSE,
            transaction_type=TransactionType.SELL,
            quantity=5,
            order_type=OrderType.MARKET,
        )
        assert req.estimated_value() is None


class TestOrder:
    def test_defaults(self):
        o = Order()
        assert o.order_id == ""
        assert o.status == OrderStatus.PENDING
        assert o.quantity == 0

    def test_full_order(self):
        o = Order(
            order_id="O123",
            exchange_segment=ExchangeSegment.NSE,
            transaction_type=TransactionType.BUY,
            quantity=100,
            price=Decimal("150.50"),
            order_type=OrderType.LIMIT,
            status=OrderStatus.EXECUTED,
            filled_quantity=100,
            average_price=Decimal("150.50"),
        )
        assert o.order_id == "O123"


class TestPosition:
    def test_defaults(self):
        p = Position()
        assert p.net_quantity == 0
        assert p.unrealized_pnl == Decimal("0")

    def test_long_position(self):
        p = Position(
            quantity=100,
            buy_quantity=100,
            net_quantity=100,
            buy_average_price=Decimal("2000"),
            last_price=Decimal("2100"),
        )
        assert p.net_quantity == 100
        assert p.pnl() == Decimal("10000")

    def test_short_position(self):
        p = Position(
            quantity=-50,
            sell_quantity=50,
            net_quantity=-50,
            sell_average_price=Decimal("2000"),
            last_price=Decimal("2100"),
        )
        assert p.net_quantity == -50
        assert p.pnl() == Decimal("-5000")


class TestHolding:
    def test_defaults(self):
        h = Holding()
        assert h.quantity == 0

    def test_pnl(self):
        h = Holding(quantity=100, cost_price=Decimal("100"), last_price=Decimal("120"))
        assert h.pnl() == Decimal("2000")


class TestTrade:
    def test_defaults(self):
        t = Trade()
        assert t.trade_id == ""

    def test_value(self):
        t = Trade(quantity=10, price=Decimal("1500"))
        assert t.value() == Decimal("15000")


class TestFundLimits:
    def test_defaults(self):
        f = FundLimits()
        assert f.available_balance == Decimal("0")

    def test_has_sufficient(self):
        f = FundLimits(available_balance=Decimal("50000"))
        assert f.has_sufficient(Decimal("30000")) is True
        assert f.has_sufficient(Decimal("60000")) is False


class TestOrderResponse:
    def test_success(self):
        r = OrderResponse.create_success(order_id="O123")
        assert r.success is True
        assert r.order_id == "O123"

    def test_failure(self):
        r = OrderResponse.create_failure("insufficient funds")
        assert r.success is False
        assert r.message == "insufficient funds"


class TestQuote:
    def test_defaults(self):
        q = Quote()
        assert q.last_price == Decimal("0")

    def test_change_pct(self):
        q = Quote(
            last_price=Decimal("110"),
            close=Decimal("100"),
        )
        assert q.change_pct() == Decimal("10.0")

    def test_change_pct_zero_close(self):
        q = Quote(last_price=Decimal("100"))
        assert q.change_pct() == Decimal("0")

    def test_quote_with_security_id(self):
        # Regression: the Dhan mapper passes security_id=... to Quote(...).
        # Pre-fix the field was dropped silently; the field now exists.
        q = Quote(symbol="TCS", security_id="11536", last_price=Decimal("3500"))
        assert q.security_id == "11536"

    def test_quote_without_security_id_defaults_to_none(self):
        # Default must be None so callers that don't have a security_id
        # (e.g. tests, paper broker) can still construct a Quote.
        q = Quote(symbol="TCS", last_price=Decimal("3500"))
        assert q.security_id is None


class TestHistoricalCandle:
    def test_defaults(self):
        c = HistoricalCandle()
        assert c.volume == 0

    def test_body(self):
        c = HistoricalCandle(open=Decimal("100"), close=Decimal("105"))
        assert c.body() == Decimal("5")

    def test_range(self):
        c = HistoricalCandle(high=Decimal("110"), low=Decimal("90"))
        assert c.range() == Decimal("20")


class TestOptionContract:
    def test_defaults(self):
        oc = OptionContract()
        assert oc.strike == Decimal("0")

    def test_with_data(self):
        oc = OptionContract(
            strike=Decimal("23000"),
            expiry="2025-03-27",
            ce_ltp=Decimal("150"),
            pe_ltp=Decimal("80"),
        )
        assert oc.ce_ltp == Decimal("150")
