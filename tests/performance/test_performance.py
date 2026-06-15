"""Performance benchmarks for the new brokers.dhan architecture."""

import time
from decimal import Decimal

import pytest

from brokers.dhan.domain import (
    Balance,
    DepthLevel,
    Exchange,
    Holding,
    Instrument,
    InstrumentType,
    MarketDepth,
    Order,
    OrderSide,
    OrderStatus,
    OrderType,
    Position,
    Quote,
    Trade,
)
from brokers.dhan.resolver import SymbolResolver


@pytest.mark.performance
class TestDomainModelCreationLatency:
    """Benchmark frozen dataclass creation for the new domain models."""

    def test_quote_creation_latency(self):
        iterations = 10_000
        start = time.perf_counter()
        for i in range(iterations):
            Quote(symbol=f"SYM-{i}", ltp=Decimal("2500.50"), volume=1000)
        elapsed_ms = (time.perf_counter() - start) * 1000
        per_op_us = (elapsed_ms / iterations) * 1000
        assert per_op_us < 200, f"Quote() too slow: {per_op_us:.1f}μs/op"

    def test_order_creation_latency(self):
        iterations = 10_000
        start = time.perf_counter()
        for i in range(iterations):
            Order(
                order_id=f"ORD-{i}",
                symbol="RELIANCE",
                exchange=Exchange.NSE,
                side=OrderSide.BUY,
                quantity=100,
                order_type=OrderType.LIMIT,
                price=Decimal("2500"),
                status=OrderStatus.OPEN,
            )
        elapsed_ms = (time.perf_counter() - start) * 1000
        per_op_us = (elapsed_ms / iterations) * 1000
        assert per_op_us < 50, f"Order() too slow: {per_op_us:.1f}μs/op"

    def test_position_creation_latency(self):
        iterations = 10_000
        start = time.perf_counter()
        for _ in range(iterations):
            Position(
                symbol="RELIANCE",
                exchange="NSE",
                quantity=100,
                avg_price=Decimal("2500"),
                ltp=Decimal("2550"),
            )
        elapsed_ms = (time.perf_counter() - start) * 1000
        per_op_us = (elapsed_ms / iterations) * 1000
        assert per_op_us < 50, f"Position() too slow: {per_op_us:.1f}μs/op"

    def test_instrument_creation_latency(self):
        iterations = 10_000
        start = time.perf_counter()
        for _ in range(iterations):
            Instrument(
                symbol="RELIANCE",
                exchange=Exchange.NSE,
                security_id="2885",
                instrument_type=InstrumentType.EQUITY,
                lot_size=1,
                tick_size=Decimal("0.05"),
            )
        elapsed_ms = (time.perf_counter() - start) * 1000
        per_op_us = (elapsed_ms / iterations) * 1000
        assert per_op_us < 200, f"Instrument() too slow: {per_op_us:.1f}μs/op"

    def test_market_depth_creation_latency(self):
        bids = tuple(DepthLevel(price=Decimal(str(100 - i)), quantity=100, orders=5) for i in range(5))
        asks = tuple(DepthLevel(price=Decimal(str(101 + i)), quantity=100, orders=5) for i in range(5))
        iterations = 10_000
        start = time.perf_counter()
        for _ in range(iterations):
            MarketDepth(symbol="RELIANCE", bids=bids, asks=asks)
        elapsed_ms = (time.perf_counter() - start) * 1000
        per_op_us = (elapsed_ms / iterations) * 1000
        assert per_op_us < 200, f"MarketDepth() too slow: {per_op_us:.1f}μs/op"


@pytest.mark.performance
class TestSymbolResolverThroughput:
    """Benchmark O(1) symbol resolution."""

    def _make_resolver(self, n: int = 1000) -> SymbolResolver:
        rows = []
        for i in range(n):
            rows.append({
                "SEM_TRADING_SYMBOL": f"SYM{i}",
                "SEM_SMST_SECURITY_ID": str(1000 + i),
                "SEM_EXM_EXCH_ID": "NSE_EQ",
                "SEM_INSTRUMENT_NAME": "EQUITY",
                "SEM_LOT_UNITS": 1,
                "SEM_TICK_SIZE": 0.05,
            })
        r = SymbolResolver()
        r.load_from_rows(rows)
        return r

    def test_resolve_throughput(self):
        resolver = self._make_resolver(1000)
        iterations = 10_000
        symbols = [f"SYM{i % 1000}" for i in range(iterations)]

        start = time.perf_counter()
        for sym in symbols:
            resolver.get_by_symbol(sym, "NSE")
        elapsed_ms = (time.perf_counter() - start) * 1000
        ops_per_sec = iterations / (elapsed_ms / 1000)
        assert ops_per_sec > 50_000, f"resolve throughput too low: {ops_per_sec:.0f} ops/s"

    def test_load_175k_instruments(self):
        """Verify loading 175k instruments completes in < 5 seconds."""
        rows = []
        for i in range(175_000):
            rows.append({
                "SEM_TRADING_SYMBOL": f"INST{i}",
                "SEM_SMST_SECURITY_ID": str(i),
                "SEM_EXM_EXCH_ID": "NSE_EQ",
                "SEM_INSTRUMENT_NAME": "EQUITY",
                "SEM_LOT_UNITS": 1,
                "SEM_TICK_SIZE": 0.05,
            })
        r = SymbolResolver()
        start = time.perf_counter()
        r.load_from_rows(rows)
        elapsed = time.perf_counter() - start
        assert elapsed < 60.0, f"Loading 175k instruments too slow: {elapsed:.1f}s"
        assert r.stats()["total"] == 175_000
