"""Tests for Order.from_broker_dict canonical factory."""

from __future__ import annotations

from decimal import Decimal

from brokers.common.core.domain import (
    Order,
    OrderStatus,
    OrderType,
    ProductType,
    Side,
)

# ── Pure-factory tests (no broker-specific resolver) ──────────────────────


class TestFromBrokerDictDhanShape:
    """The canonical factory should accept the Dhan REST shape out of the box."""

    def test_full_dhan_dict_produces_canonical_order(self):
        raw = {
            "orderId": "ORD001",
            "tradingSymbol": "RELIANCE",
            "exchangeSegment": "NSE_EQ",
            "transactionType": "BUY",
            "orderType": "LIMIT",
            "quantity": 10,
            "filledQty": 10,
            "price": 2450.0,
            "averagePrice": 2449.5,
            "orderStatus": "TRADED",
        }
        order = Order.from_broker_dict(raw)
        assert order.order_id == "ORD001"
        assert order.symbol == "RELIANCE"
        # Without a resolver, the segment string is preserved as-is.
        assert order.exchange == "NSE_EQ"
        assert order.side == Side.BUY
        assert order.order_type == OrderType.LIMIT
        assert order.quantity == 10
        assert order.filled_quantity == 10
        assert order.price == Decimal("2450.0")
        assert order.avg_price == Decimal("2449.5")
        # "TRADED" is normalized to FILLED.
        assert order.status == OrderStatus.FILLED
        assert order.reject_reason == ""

    def test_status_transit_normalized_to_open(self):
        raw = {
            "orderId": "ORD-T",
            "tradingSymbol": "NIFTY",
            "exchangeSegment": "NSE_FNO",
            "transactionType": "SELL",
            "orderType": "MARKET",
            "quantity": 75,
            "orderStatus": "TRANSIT",
        }
        order = Order.from_broker_dict(raw)
        assert order.status == OrderStatus.OPEN

    def test_status_complete_normalized_to_filled(self):
        raw = {
            "orderId": "ORD-C",
            "tradingSymbol": "RELIANCE",
            "exchangeSegment": "NSE_EQ",
            "transactionType": "BUY",
            "orderType": "MARKET",
            "quantity": 5,
            "orderStatus": "COMPLETE",
        }
        order = Order.from_broker_dict(raw)
        assert order.status == OrderStatus.FILLED

    def test_order_type_stoploss_limit_mapped_to_stop_loss(self):
        raw = {
            "orderId": "ORD-SL",
            "tradingSymbol": "BANKNIFTY",
            "exchangeSegment": "NSE_FNO",
            "transactionType": "BUY",
            "orderType": "STOPLOSS_LIMIT",
            "quantity": 25,
            "orderStatus": "OPEN",
        }
        order = Order.from_broker_dict(raw)
        assert order.order_type == OrderType.STOP_LOSS

    def test_order_type_stoploss_market_mapped_to_stop_loss_market(self):
        raw = {
            "orderId": "ORD-SLM",
            "tradingSymbol": "BANKNIFTY",
            "exchangeSegment": "NSE_FNO",
            "transactionType": "SELL",
            "orderType": "STOPLOSS_MARKET",
            "quantity": 25,
            "orderStatus": "OPEN",
        }
        order = Order.from_broker_dict(raw)
        assert order.order_type == OrderType.STOP_LOSS_MARKET

    def test_order_type_sl_alias_mapped_to_stop_loss(self):
        raw = {
            "orderId": "ORD-S",
            "tradingSymbol": "X",
            "exchangeSegment": "NSE_EQ",
            "transactionType": "BUY",
            "orderType": "SL",
            "quantity": 1,
            "orderStatus": "OPEN",
        }
        order = Order.from_broker_dict(raw)
        assert order.order_type == OrderType.STOP_LOSS

    def test_order_type_slm_alias_mapped_to_stop_loss_market(self):
        raw = {
            "orderId": "ORD-M",
            "tradingSymbol": "X",
            "exchangeSegment": "NSE_EQ",
            "transactionType": "BUY",
            "orderType": "SLM",
            "quantity": 1,
            "orderStatus": "OPEN",
        }
        order = Order.from_broker_dict(raw)
        assert order.order_type == OrderType.STOP_LOSS_MARKET

    def test_order_type_market_passes_through(self):
        raw = {
            "orderId": "ORD-MK",
            "tradingSymbol": "X",
            "exchangeSegment": "NSE_EQ",
            "transactionType": "BUY",
            "orderType": "MARKET",
            "quantity": 1,
            "orderStatus": "OPEN",
        }
        order = Order.from_broker_dict(raw)
        assert order.order_type == OrderType.MARKET

    def test_unknown_order_type_falls_back_to_market(self):
        raw = {
            "orderId": "ORD-X",
            "tradingSymbol": "X",
            "exchangeSegment": "NSE_EQ",
            "transactionType": "BUY",
            "orderType": "GIBBERISH",
            "quantity": 1,
            "orderStatus": "OPEN",
        }
        order = Order.from_broker_dict(raw)
        assert order.order_type == OrderType.MARKET

    def test_empty_dict_produces_defaults(self):
        order = Order.from_broker_dict({})
        assert order.order_id == ""
        assert order.symbol == ""
        # No exchangeSegment and no resolver -> "NSE" fallback.
        assert order.exchange == "NSE"
        assert order.side == Side.BUY
        assert order.order_type == OrderType.MARKET
        assert order.quantity == 0
        assert order.filled_quantity == 0
        assert order.price == Decimal("0")
        assert order.avg_price == Decimal("0")
        assert order.status == OrderStatus.OPEN
        assert order.reject_reason == ""

    def test_side_sell_parsed_correctly(self):
        raw = {
            "orderId": "ORD-S",
            "tradingSymbol": "RELIANCE",
            "exchangeSegment": "NSE_EQ",
            "transactionType": "SELL",
            "orderType": "MARKET",
            "quantity": 5,
            "orderStatus": "OPEN",
        }
        order = Order.from_broker_dict(raw)
        assert order.side == Side.SELL

    def test_side_case_insensitive(self):
        raw = {
            "orderId": "ORD-L",
            "tradingSymbol": "X",
            "exchangeSegment": "NSE_EQ",
            "transactionType": "buy",
            "orderType": "MARKET",
            "quantity": 1,
            "orderStatus": "OPEN",
        }
        order = Order.from_broker_dict(raw)
        assert order.side == Side.BUY

    def test_missing_price_and_average_price_default_to_zero(self):
        raw = {
            "orderId": "ORD-NP",
            "tradingSymbol": "X",
            "exchangeSegment": "NSE_EQ",
            "transactionType": "BUY",
            "orderType": "MARKET",
            "quantity": 1,
            "orderStatus": "OPEN",
        }
        order = Order.from_broker_dict(raw)
        assert order.price == Decimal("0")
        assert order.avg_price == Decimal("0")

    def test_none_price_treated_as_zero(self):
        raw = {
            "orderId": "ORD-N",
            "tradingSymbol": "X",
            "exchangeSegment": "NSE_EQ",
            "transactionType": "BUY",
            "orderType": "MARKET",
            "quantity": 1,
            "price": None,
            "averagePrice": None,
            "orderStatus": "OPEN",
        }
        order = Order.from_broker_dict(raw)
        assert order.price == Decimal("0")
        assert order.avg_price == Decimal("0")

    def test_reject_reason_populated(self):
        raw = {
            "orderId": "ORD-R",
            "tradingSymbol": "X",
            "exchangeSegment": "NSE_EQ",
            "transactionType": "BUY",
            "orderType": "MARKET",
            "quantity": 1,
            "orderStatus": "REJECTED",
            "rejectReason": "Insufficient funds",
        }
        order = Order.from_broker_dict(raw)
        assert order.status == OrderStatus.REJECTED
        assert order.reject_reason == "Insufficient funds"

    def test_defaults_to_default_product_type(self):
        raw = {
            "orderId": "ORD-D",
            "tradingSymbol": "X",
            "exchangeSegment": "NSE_EQ",
            "transactionType": "BUY",
            "orderType": "MARKET",
            "quantity": 1,
            "orderStatus": "OPEN",
        }
        order = Order.from_broker_dict(raw)
        assert order.product_type == ProductType.INTRADAY
        assert order.filled_quantity == 0

    def test_snake_case_fallback_for_alternative_callers(self):
        raw = {
            "order_id": "ORD-S",
            "symbol": "RELIANCE",
            "exchange": "NSE",
            "side": "SELL",
            "order_type": "LIMIT",
            "quantity": 3,
            "filled_quantity": 2,
            "price": "100.5",
            "average_price": "100.0",
            "status": "PARTIALLY_FILLED",
            "reject_reason": "x",
        }
        order = Order.from_broker_dict(raw)
        assert order.order_id == "ORD-S"
        assert order.symbol == "RELIANCE"
        assert order.exchange == "NSE"
        assert order.side == Side.SELL
        assert order.order_type == OrderType.LIMIT
        assert order.quantity == 3
        assert order.filled_quantity == 2
        assert order.price == Decimal("100.5")
        assert order.avg_price == Decimal("100.0")
        assert order.status == OrderStatus.PARTIALLY_FILLED
        assert order.reject_reason == "x"


# ── Resolver-aware tests ──────────────────────────────────────────────────


class TestFromBrokerDictWithExchangeResolver:
    """The optional ``exchange_resolver`` lets adapters map segments to enums."""

    def test_exchange_resolver_invoked_with_segment_string(self):
        captured: list[str] = []

        def resolver(seg: str) -> str:
            captured.append(seg)
            return f"EX::{seg}"

        raw = {
            "orderId": "ORD-R",
            "tradingSymbol": "X",
            "exchangeSegment": "NSE_EQ",
            "transactionType": "BUY",
            "orderType": "MARKET",
            "quantity": 1,
            "orderStatus": "OPEN",
        }
        order = Order.from_broker_dict(raw, exchange_resolver=resolver)
        assert captured == ["NSE_EQ"]
        assert order.exchange == "EX::NSE_EQ"

    def test_exchange_resolver_can_map_to_dhan_exchange_enum(self):
        from brokers.dhan.domain import Exchange as DhanExchange

        def dhan_resolver(seg: str) -> DhanExchange:
            from brokers.dhan.segments import SEGMENT_TO_EXCHANGE
            return DhanExchange(SEGMENT_TO_EXCHANGE.get(str(seg), "NSE"))

        raw = {
            "orderId": "ORD-D",
            "tradingSymbol": "RELIANCE",
            "exchangeSegment": "NSE_EQ",
            "transactionType": "BUY",
            "orderType": "MARKET",
            "quantity": 1,
            "orderStatus": "OPEN",
        }
        order = Order.from_broker_dict(raw, exchange_resolver=dhan_resolver)
        assert order.exchange == DhanExchange.NSE

    def test_no_resolver_falls_back_to_segment_string(self):
        raw = {
            "orderId": "ORD-N",
            "tradingSymbol": "X",
            "exchangeSegment": "BSE_FNO",
            "transactionType": "BUY",
            "orderType": "MARKET",
            "quantity": 1,
            "orderStatus": "OPEN",
        }
        order = Order.from_broker_dict(raw)
        assert order.exchange == "BSE_FNO"
