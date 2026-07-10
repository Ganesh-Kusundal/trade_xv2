"""Upstox Market Data Integration Tests (P6-1).

Tests that verify market data operations through Upstox adapter:
- WebSocket subscription lifecycle
- Tick data reception and translation
- Quote accuracy
- Depth feed parsing
- Unsubscription cleanup
- Concurrent stream operations
- Error handling for market data

Run with:
    pytest tests/integration/test_upstox_market_data.py -v
"""

from __future__ import annotations

import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from decimal import Decimal

import pytest

from brokers.upstox.gateway import UpstoxBrokerGateway
from domain import MarketDepth, Quote
from tests.integration.fixtures.upstox import (
    make_depth_response,
    make_instrument_defn,
    make_mock_broker,
    make_quote_response,
    make_tick_payload,
    mock_market_quote,
)

# ─── Fixtures ──────────────────────────────────────────────────────────────


@pytest.fixture
def mock_broker_connected():
    """Create a mock broker with connected WebSocket."""
    return make_mock_broker(ws_connected=True)


@pytest.fixture
def mock_broker_disconnected():
    """Create a mock broker with disconnected WebSocket."""
    return make_mock_broker(ws_connected=False)


@pytest.fixture
def gateway_connected(mock_broker_connected):
    """Create gateway with connected WebSocket."""
    return UpstoxBrokerGateway(mock_broker_connected)


@pytest.fixture
def gateway_disconnected(mock_broker_disconnected):
    """Create gateway with disconnected WebSocket."""
    return UpstoxBrokerGateway(mock_broker_disconnected)


@pytest.fixture
def instrument_defn():
    """Create standard RELIANCE instrument definition."""
    return make_instrument_defn(
        name="RELIANCE",
        symbol="RELIANCE",
        instrument_key="NSE_EQ|RELIANCE",
        exchange_segment="NSE_EQ",
    )


@pytest.fixture
def nifty_index_defn():
    """Create NIFTY index instrument definition."""
    return make_instrument_defn(
        name="NIFTY 50",
        symbol="NIFTY",
        instrument_key="NSE_INDEX|NIFTY 50",
        exchange_segment="NSE_INDEX",
    )


# ─── WebSocket Subscription ───────────────────────────────────────────────


class TestWebSocketSubscription:
    """Test WebSocket subscription lifecycle."""

    def test_stream_subscribes_when_connected(self, gateway_connected):
        """stream() should subscribe when WebSocket is already connected."""
        ws = gateway_connected.stream("RELIANCE", exchange="NSE", mode="LTP")

        assert ws is not None
        assert len(gateway_connected._broker.market_data_websocket.subscribed) == 1

        keys, mode = gateway_connected._broker.market_data_websocket.subscribed[0]
        assert "NSE|RELIANCE" in keys
        assert mode == "ltp"

    def test_stream_connects_when_disconnected(self, gateway_disconnected):
        """stream() should initiate connect when WebSocket is not connected."""
        ws = gateway_disconnected.stream("RELIANCE", exchange="NSE", mode="LTP")

        assert ws is not None
        # Connect should be scheduled (async)
        assert gateway_disconnected._broker.market_data_websocket.connect_called

    def test_stream_registers_callback(self, gateway_connected):
        """stream() should register on_tick callback."""
        received = []
        gateway_connected.stream(
            "RELIANCE",
            exchange="NSE",
            mode="LTP",
            on_tick=received.append,
        )

        assert len(gateway_connected._broker.market_data_websocket.listeners) == 1

    def test_stream_deduplicates_callbacks(self, gateway_connected):
        """stream() should not register same callback twice."""

        def on_tick(tick):
            pass

        gateway_connected.stream("RELIANCE", exchange="NSE", mode="LTP", on_tick=on_tick)
        gateway_connected.stream("RELIANCE", exchange="NSE", mode="LTP", on_tick=on_tick)

        # Should only have one listener
        assert len(gateway_connected._broker.market_data_websocket.listeners) == 1

    def test_stream_with_no_callback(self, gateway_connected):
        """stream() should work without on_tick callback."""
        ws = gateway_connected.stream("RELIANCE", exchange="NSE", mode="LTP")

        assert ws is not None
        # No listener registered
        assert len(gateway_connected._broker.market_data_websocket.listeners) == 0

    def test_stream_accepts_full_mode(self, gateway_connected):
        """stream() should accept FULL mode."""
        gateway_connected.stream("RELIANCE", exchange="NSE", mode="FULL")

        _keys, mode = gateway_connected._broker.market_data_websocket.subscribed[0]
        assert mode == "full"

    def test_stream_accepts_option_greeks_mode(self, gateway_connected):
        """stream() should accept option_greeks mode."""
        gateway_connected.stream("NIFTY", exchange="NFO", mode="option_greeks")

        _keys, mode = gateway_connected._broker.market_data_websocket.subscribed[0]
        assert mode == "option_greeks"

    def test_stream_maps_nse_exchange(self, gateway_connected):
        """stream() should map NSE exchange to NSE segment."""
        gateway_connected.stream("RELIANCE", exchange="NSE", mode="LTP")

        keys, _ = gateway_connected._broker.market_data_websocket.subscribed[0]
        assert "NSE|RELIANCE" in keys

    def test_stream_maps_bse_exchange(self, gateway_connected):
        """stream() should map BSE exchange to BSE segment."""
        gateway_connected.stream("INFY", exchange="BSE", mode="LTP")

        keys, _ = gateway_connected._broker.market_data_websocket.subscribed[0]
        assert "BSE|INFY" in keys

    def test_stream_maps_nfo_exchange(self, gateway_connected):
        """stream() should map NFO exchange correctly."""
        gateway_connected.stream("NIFTY", exchange="NFO", mode="FULL")

        keys, _ = gateway_connected._broker.market_data_websocket.subscribed[0]
        # NFO maps to NFO segment (not NSE_FO)
        assert "NFO|NIFTY" in keys


# ─── Tick Data Reception ─────────────────────────────────────────────────


class TestTickDataReception:
    """Test tick data reception and translation."""

    def test_tick_translated_to_quote(self, gateway_connected, instrument_defn):
        """Received ticks should be translated to Quote objects."""
        gateway_connected._broker.instrument_resolver.resolve.return_value = instrument_defn

        received = []
        gateway_connected.stream(
            "RELIANCE",
            exchange="NSE",
            mode="LTP",
            on_tick=received.append,
        )

        # Simulate tick
        gateway_connected._broker.market_data_websocket.simulate_tick(
            "tick",
            make_tick_payload("NSE_EQ|RELIANCE", last_price=2500.50, close_price=2475.0),
        )

        assert len(received) == 1
        tick = received[0]
        assert isinstance(tick, Quote)
        assert tick.ltp == Decimal("2500.50")
        assert tick.symbol == "RELIANCE"

    def test_tick_with_full_data(self, gateway_connected, instrument_defn):
        """Full tick should include bid/ask data."""
        gateway_connected._broker.instrument_resolver.resolve.return_value = instrument_defn

        received = []
        gateway_connected.stream(
            "RELIANCE",
            exchange="NSE",
            mode="FULL",
            on_tick=received.append,
        )

        tick_data = make_tick_payload("NSE_EQ|RELIANCE", last_price=2500.50)
        tick_data["payload"]["best_bid_price"] = 2500.00
        tick_data["payload"]["best_ask_price"] = 2501.00
        tick_data["frame_type"] = "full"

        gateway_connected._broker.market_data_websocket.simulate_tick("tick", tick_data)

        assert len(received) == 1
        quote = received[0]
        assert isinstance(quote, Quote)
        assert quote.bid == Decimal("2500.00")
        assert quote.ask == Decimal("2501.00")

    def test_tick_with_volume(self, gateway_connected, instrument_defn):
        """Tick should include volume data."""
        gateway_connected._broker.instrument_resolver.resolve.return_value = instrument_defn

        received = []
        gateway_connected.stream(
            "RELIANCE",
            exchange="NSE",
            mode="LTP",
            on_tick=received.append,
        )

        gateway_connected._broker.market_data_websocket.simulate_tick(
            "tick",
            make_tick_payload("NSE_EQ|RELIANCE", last_price=2500.0, volume=100000),
        )

        quote = received[0]
        assert quote.volume == 100000

    def test_tick_change_calculation(self, gateway_connected, instrument_defn):
        """Tick should calculate change from close price."""
        gateway_connected._broker.instrument_resolver.resolve.return_value = instrument_defn

        received = []
        gateway_connected.stream(
            "RELIANCE",
            exchange="NSE",
            mode="LTP",
            on_tick=received.append,
        )

        gateway_connected._broker.market_data_websocket.simulate_tick(
            "tick",
            make_tick_payload("NSE_EQ|RELIANCE", last_price=2500.0, close_price=2475.0),
        )

        quote = received[0]
        assert quote.change == Decimal("25.0")

    def test_unresolvable_tick_returns_raw_dict(self, gateway_connected):
        """Tick with unresolvable instrument key should return raw dict."""
        gateway_connected._broker.instrument_resolver.resolve.return_value = None

        received = []
        gateway_connected.stream(
            "UNKNOWN",
            exchange="NSE",
            mode="LTP",
            on_tick=received.append,
        )

        gateway_connected._broker.market_data_websocket.simulate_tick(
            "tick",
            {"frame_type": "ltpc", "payload": {"last_price": 100.0}},
        )

        assert len(received) == 1
        assert isinstance(received[0], dict)


# ─── Unsubscription Cleanup ─────────────────────────────────────────────


class TestUnsubscriptionCleanup:
    """Test unsubscription and cleanup."""

    def test_unstream_removes_callback(self, gateway_connected, instrument_defn):
        """unstream() should remove specific callback."""

        def on_tick(tick):
            pass

        gateway_connected.stream("RELIANCE", exchange="NSE", mode="LTP", on_tick=on_tick)
        assert len(gateway_connected._broker.market_data_websocket.listeners) == 1

        gateway_connected.unstream("RELIANCE", exchange="NSE", on_tick=on_tick)
        assert len(gateway_connected._broker.market_data_websocket.listeners) == 0

    def test_unstream_removes_all_callbacks(self, gateway_connected):
        """unstream() with no callback should remove all callbacks for instrument."""

        def on_tick1(tick):
            pass

        def on_tick2(tick):
            pass

        gateway_connected.stream("RELIANCE", exchange="NSE", mode="LTP", on_tick=on_tick1)
        gateway_connected.stream("RELIANCE", exchange="NSE", mode="LTP", on_tick=on_tick2)
        assert len(gateway_connected._broker.market_data_websocket.listeners) == 2

        gateway_connected.unstream("RELIANCE", exchange="NSE")
        assert len(gateway_connected._broker.market_data_websocket.listeners) == 0

    def test_unstream_unsubscribes_from_websocket(self, gateway_connected):
        """unstream() should unsubscribe from WebSocket."""

        def on_tick(tick):
            pass

        gateway_connected.stream("RELIANCE", exchange="NSE", mode="LTP", on_tick=on_tick)
        gateway_connected.unstream("RELIANCE", exchange="NSE", on_tick=on_tick)

        assert len(gateway_connected._broker.market_data_websocket._unsubscriptions) == 1
        keys = gateway_connected._broker.market_data_websocket._unsubscriptions[0]
        assert "NSE|RELIANCE" in keys

    def test_unstream_clears_registry_entry(self, gateway_connected):
        """unstream() should remove instrument from stream registry."""

        def on_tick(tick):
            pass

        gateway_connected.stream("RELIANCE", exchange="NSE", mode="LTP", on_tick=on_tick)
        assert "NSE|RELIANCE" in gateway_connected._stream_registry

        gateway_connected.unstream("RELIANCE", exchange="NSE", on_tick=on_tick)
        assert "NSE|RELIANCE" not in gateway_connected._stream_registry

    def test_unstream_nonexistent_instrument(self, gateway_connected):
        """unstream() for non-existent instrument should not raise."""
        gateway_connected.unstream("UNKNOWN", exchange="NSE")
        # Should not raise

    def test_multiple_instruments_independent(self, gateway_connected):
        """Multiple instruments should have independent subscriptions."""

        def on_tick1(tick):
            pass

        def on_tick2(tick):
            pass

        gateway_connected.stream("RELIANCE", exchange="NSE", mode="LTP", on_tick=on_tick1)
        gateway_connected.stream("TCS", exchange="NSE", mode="LTP", on_tick=on_tick2)

        assert len(gateway_connected._stream_registry) == 2
        assert "NSE|RELIANCE" in gateway_connected._stream_registry
        assert "NSE|TCS" in gateway_connected._stream_registry

        # Unsubscribe only RELIANCE
        gateway_connected.unstream("RELIANCE", exchange="NSE", on_tick=on_tick1)

        assert "NSE|RELIANCE" not in gateway_connected._stream_registry
        assert "NSE|TCS" in gateway_connected._stream_registry


# ─── Quote Accuracy ──────────────────────────────────────────────────────


class TestQuoteAccuracy:
    """Test quote data accuracy."""

    def test_ltp_accuracy(self, mock_broker_connected, instrument_defn):
        """ltp() should return accurate price."""
        mock_broker_connected.instrument_resolver.resolve.return_value = instrument_defn
        mock_market_quote(mock_broker_connected, "RELIANCE", 2500.50)

        gateway = UpstoxBrokerGateway(mock_broker_connected)
        result = gateway.ltp("RELIANCE", "NSE")

        assert result == Decimal("2500.5000")

    def test_quote_ohlcv_accuracy(self, mock_broker_connected, instrument_defn):
        """quote() should return accurate OHLCV data."""
        mock_broker_connected.instrument_resolver.resolve.return_value = instrument_defn
        mock_broker_connected.market_data_v2.get_quote.return_value = make_quote_response(
            "RELIANCE",
            last_price=2500.50,
            open=2480.00,
            high=2520.00,
            low=2475.00,
            close=2475.00,
            volume=1000000,
            net_change=25.50,
        )

        gateway = UpstoxBrokerGateway(mock_broker_connected)
        result = gateway.quote("RELIANCE", "NSE")

        assert result.ltp == Decimal("2500.5000")
        assert result.open == Decimal("2480.0000")
        assert result.high == Decimal("2520.0000")
        assert result.low == Decimal("2475.0000")
        assert result.close == Decimal("2475.0000")
        assert result.volume == 1000000
        assert result.change == Decimal("25.5000")

    def test_depth_accuracy(self, mock_broker_connected, instrument_defn):
        """depth() should return accurate depth data."""
        mock_broker_connected.instrument_resolver.resolve.return_value = instrument_defn
        mock_broker_connected.market_data_v2.get_order_book.return_value = make_depth_response(
            "RELIANCE",
            bids=[
                {"price": 2500.00, "quantity": 100, "orders": 5},
                {"price": 2499.00, "quantity": 200, "orders": 3},
            ],
            asks=[
                {"price": 2501.00, "quantity": 150, "orders": 4},
                {"price": 2502.00, "quantity": 250, "orders": 2},
            ],
        )

        gateway = UpstoxBrokerGateway(mock_broker_connected)
        result = gateway.depth("RELIANCE", "NSE")

        assert isinstance(result, MarketDepth)
        assert len(result.bids) == 2
        assert len(result.asks) == 2
        assert result.bids[0].price == Decimal("2500.0000")
        assert result.bids[0].quantity == 100
        assert result.asks[0].price == Decimal("2501.0000")
        assert result.asks[0].quantity == 150


# ─── Concurrent Market Data ─────────────────────────────────────────────


class TestConcurrentMarketData:
    """Test concurrent market data operations."""

    def test_concurrent_subscriptions(self, gateway_connected):
        """Concurrent subscriptions should not corrupt state."""
        errors = []
        subscribed = []
        lock = threading.Lock()

        def subscribe(symbol: str):
            try:

                def on_tick(tick):
                    pass

                gateway_connected.stream(symbol, exchange="NSE", mode="LTP", on_tick=on_tick)
                with lock:
                    subscribed.append(symbol)
            except Exception as e:
                with lock:
                    errors.append(e)

        symbols = [f"SYM{i}" for i in range(20)]
        with ThreadPoolExecutor(max_workers=10) as executor:
            futures = [executor.submit(subscribe, sym) for sym in symbols]
            for f in as_completed(futures):
                f.result()

        assert len(errors) == 0
        assert len(subscribed) == 20
        assert len(gateway_connected._stream_registry) == 20

    def test_concurrent_subscribe_unsubscribe(self, gateway_connected):
        """Concurrent subscribe/unsubscribe should be safe."""
        errors = []

        def subscribe_unsubscribe(i: int):
            try:

                def on_tick(tick):
                    pass

                symbol = f"SYM{i}"
                gateway_connected.stream(symbol, exchange="NSE", mode="LTP", on_tick=on_tick)
                gateway_connected.unstream(symbol, exchange="NSE", on_tick=on_tick)
            except Exception as e:
                errors.append(e)

        with ThreadPoolExecutor(max_workers=5) as executor:
            futures = [executor.submit(subscribe_unsubscribe, i) for i in range(10)]
            for f in as_completed(futures):
                f.result()

        assert len(errors) == 0

    def test_concurrent_tick_processing(self, gateway_connected, instrument_defn):
        """Concurrent tick processing should be safe."""
        gateway_connected._broker.instrument_resolver.resolve.return_value = instrument_defn

        received = []
        lock = threading.Lock()

        def on_tick(tick):
            with lock:
                received.append(tick)

        gateway_connected.stream(
            "RELIANCE",
            exchange="NSE",
            mode="LTP",
            on_tick=on_tick,
        )

        # Simulate concurrent ticks
        def send_tick(price: float):
            gateway_connected._broker.market_data_websocket.simulate_tick(
                "tick",
                make_tick_payload("NSE_EQ|RELIANCE", last_price=price),
            )

        with ThreadPoolExecutor(max_workers=10) as executor:
            futures = [executor.submit(send_tick, 2500.0 + i * 0.1) for i in range(20)]
            for f in as_completed(futures):
                f.result()

        # Small delay for async processing
        time.sleep(0.1)
        assert len(received) == 20


# ─── Error Handling ──────────────────────────────────────────────────────


class TestMarketDataErrorHandling:
    """Test market data error scenarios."""

    def test_ltp_with_network_error(self, mock_broker_connected, instrument_defn):
        """ltp() should handle network errors gracefully."""
        mock_broker_connected.instrument_resolver.resolve.return_value = instrument_defn
        mock_broker_connected.market_data_v2.get_quote.side_effect = ConnectionError("Timeout")

        gateway = UpstoxBrokerGateway(mock_broker_connected)

        with pytest.raises(ConnectionError):
            gateway.ltp("RELIANCE", "NSE")

    def test_quote_with_empty_response(self, mock_broker_connected, instrument_defn):
        """quote() should handle empty response gracefully."""
        mock_broker_connected.instrument_resolver.resolve.return_value = instrument_defn
        mock_broker_connected.market_data_v2.get_quote.return_value = {"data": {}}

        gateway = UpstoxBrokerGateway(mock_broker_connected)
        result = gateway.quote("RELIANCE", "NSE")

        assert isinstance(result, Quote)
        assert result.ltp == Decimal("0")

    def test_depth_with_empty_response(self, mock_broker_connected, instrument_defn):
        """depth() should handle empty response gracefully."""
        mock_broker_connected.instrument_resolver.resolve.return_value = instrument_defn
        mock_broker_connected.market_data_v2.get_order_book.return_value = {"data": {}}

        gateway = UpstoxBrokerGateway(mock_broker_connected)
        result = gateway.depth("RELIANCE", "NSE")

        assert isinstance(result, MarketDepth)
        assert len(result.bids) == 0
        assert len(result.asks) == 0

    def test_stream_unsubscribe_failure_handled(self, mock_broker_connected):
        """stream() should handle unsubscribe failure gracefully."""
        # Make unsubscribe raise an error

        def failing_unsubscribe(keys):
            raise RuntimeError("Unsubscribe failed")

        mock_broker_connected.market_data_websocket.unsubscribe = failing_unsubscribe

        def on_tick(tick):
            pass

        gateway = UpstoxBrokerGateway(mock_broker_connected)
        gateway.stream("RELIANCE", exchange="NSE", mode="LTP", on_tick=on_tick)

        # Should not raise even if unsubscribe fails
        gateway.unstream("RELIANCE", exchange="NSE", on_tick=on_tick)


# ─── Live read-only depth (gated) ─────────────────────────────────────────

from tests.integration.brokers.upstox.conftest import skip_live


@skip_live
@pytest.mark.upstox_live_readonly
class TestUpstoxDepthLive:
    def test_depth_live_levels(self, gateway):
        depth = gateway.depth("RELIANCE", "NSE")
        assert len(depth.bids) >= 1
        assert len(depth.asks) >= 1
        assert len(depth.bids) <= 5
        assert len(depth.asks) <= 5
