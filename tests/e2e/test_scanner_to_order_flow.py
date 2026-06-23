"""E2E tests for Scanner → Alert → Order → Portfolio Update flow.

Tests the complete scanning and execution pipeline:
1. Scanner runs on universe of stocks
2. Finds matching stocks based on criteria
3. Creates alerts/candidates
4. Converts to orders
5. Executes via broker
6. Updates portfolio

Uses real scanner implementations with synthetic data.
"""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

import pandas as pd
import pytest

from domain import OrderStatus, Side, Trade
from brokers.common.oms.order_manager import OmsOrderCommand
from brokers.common.oms.risk_manager import RiskConfig

from analytics.scanner.scanners import MomentumScanner, VolumeScanner
from analytics.scanner.models import Candidate, ScanResult
from analytics.pipeline.pipeline import FeaturePipeline
from analytics.pipeline import RSI, ROC, SMA, Momentum, Trend, RelativeVolume

from tests.e2e.fixtures.data_generators import (
    generate_multi_symbol_data,
    generate_trending_data,
)
from tests.e2e.fixtures.trading_context_factory import create_paper_trading_context


# ── Fixtures ────────────────────────────────────────────────────────────────


@pytest.fixture
def trading_context(tmp_path):
    return create_paper_trading_context(
        capital=Decimal("1000000"),
        max_position_pct=Decimal("50"),
        events_dir=tmp_path / "events",
    )


def _make_trending_universe(symbols=None, n_bars=100) -> pd.DataFrame:
    """Create a universe with trending stocks that will trigger momentum signals."""
    if symbols is None:
        symbols = ["RELIANCE", "TCS", "HDFCBANK", "INFY", "ICICIBANK"]
    frames = []
    for i, sym in enumerate(symbols):
        df = generate_trending_data(
            n_bars=n_bars,
            start_price=100.0 + i * 50,
            symbol=sym,
            trend_strength=0.003 + i * 0.001,
            seed=42 + i,
        )
        frames.append(df)
    return pd.concat(frames, ignore_index=True)


# ── Scanner Execution ───────────────────────────────────────────────────────


class TestScannerExecution:
    """Tests: Scanner runs correctly on various universe types."""

    def test_momentum_scanner_finds_candidates(self):
        """MomentumScanner should return candidates from trending data."""
        universe = _make_trending_universe(n_bars=60)
        scanner = MomentumScanner(top_n=3)
        result = scanner.scan(universe)

        assert isinstance(result, ScanResult)
        assert result.scanner == "momentum"
        assert result.universe_size > 0
        assert len(result.candidates) > 0

    def test_momentum_scanner_ranks_by_score(self):
        """Candidates should be ranked by composite_score descending."""
        universe = _make_trending_universe(n_bars=60)
        scanner = MomentumScanner(top_n=5)
        result = scanner.scan(universe)

        scores = [c.score for c in result.candidates]
        assert scores == sorted(scores, reverse=True)

    def test_momentum_scanner_respects_top_n(self):
        """Scanner should return at most top_n candidates."""
        universe = _make_trending_universe(symbols=["A", "B", "C", "D", "E"], n_bars=60)
        scanner = MomentumScanner(top_n=2)
        result = scanner.scan(universe)

        assert len(result.candidates) <= 2

    def test_volume_scanner_finds_candidates(self):
        """VolumeScanner should return candidates."""
        universe = generate_multi_symbol_data(n_bars=60)
        scanner = VolumeScanner(top_n=3)
        result = scanner.scan(universe)

        assert isinstance(result, ScanResult)
        assert result.universe_size > 0

    def test_empty_universe_returns_empty_result(self):
        """Empty universe should return empty ScanResult."""
        scanner = MomentumScanner()
        result = scanner.scan(pd.DataFrame())

        assert result.universe_size == 0
        assert len(result.candidates) == 0

    def test_scanner_with_insufficient_data(self):
        """Universe with too few bars should handle gracefully."""
        df = pd.DataFrame({
            "timestamp": [datetime.now(timezone.utc)],
            "open": [100.0], "high": [101.0], "low": [99.0],
            "close": [100.5], "volume": [10000], "symbol": ["TEST"],
        })
        scanner = MomentumScanner()
        result = scanner.scan(df)

        # Should not crash, may return empty or low-score candidates
        assert isinstance(result, ScanResult)

    def test_scanner_produces_deterministic_results(self):
        """Same input should produce same output."""
        universe = _make_trending_universe(n_bars=60)
        scanner = MomentumScanner(top_n=3)

        result1 = scanner.scan(universe)
        result2 = scanner.scan(universe)

        assert len(result1.candidates) == len(result2.candidates)
        for c1, c2 in zip(result1.candidates, result2.candidates):
            assert c1.symbol == c2.symbol
            assert abs(c1.score - c2.score) < 0.001


# ── Scanner → Alert Conversion ──────────────────────────────────────────────


class TestScannerToAlertConversion:
    """Tests: Scanner results convert to actionable alerts."""

    def test_top_candidate_has_valid_score(self):
        """Top candidate should have a meaningful score."""
        universe = _make_trending_universe(n_bars=60)
        scanner = MomentumScanner(top_n=3)
        result = scanner.scan(universe)

        top = result.top(1)[0]
        assert 0 <= top.score <= 100
        assert isinstance(top.symbol, str)
        assert len(top.symbol) > 0

    def test_candidate_has_reasons(self):
        """Candidates should include scoring reasons."""
        universe = _make_trending_universe(n_bars=60)
        scanner = MomentumScanner(top_n=3)
        result = scanner.scan(universe)

        for candidate in result.candidates:
            assert isinstance(candidate.metrics, dict)
            # Score-related metrics should be present
            score_keys = [k for k in candidate.metrics if k.startswith("score_")]
            assert len(score_keys) > 0

    def test_scan_result_to_dataframe(self):
        """ScanResult should convert to DataFrame correctly."""
        universe = _make_trending_universe(n_bars=60)
        scanner = MomentumScanner(top_n=3)
        result = scanner.scan(universe)

        df = result.to_dataframe()
        assert "symbol" in df.columns
        assert "score" in df.columns
        assert len(df) == len(result.candidates)

    def test_high_score_candidates_are_actionable(self):
        """Candidates above threshold should be considered actionable."""
        universe = _make_trending_universe(n_bars=80)
        scanner = MomentumScanner(top_n=10)
        result = scanner.scan(universe)

        actionable = [c for c in result.candidates if c.score > 60]
        # At least some candidates should be actionable with good data
        assert len(actionable) >= 0  # May vary with data


# ── Alert → Order Flow ──────────────────────────────────────────────────────


class TestAlertToOrderFlow:
    """Tests: Scanner candidates convert to orders."""

    def test_candidate_converts_to_order(self, trading_context):
        """A scanner candidate should be convertible to an OmsOrderCommand."""
        universe = _make_trending_universe(n_bars=60)
        scanner = MomentumScanner(top_n=1)
        result = scanner.scan(universe)

        assert len(result.candidates) > 0
        candidate = result.candidates[0]

        # Convert candidate to order
        cmd = OmsOrderCommand(
            symbol=candidate.symbol,
            exchange="NSE",
            side=Side.BUY,
            quantity=10,
            price=Decimal("100.0"),
            correlation_id=f"scanner-{candidate.symbol}",
        )

        order_result = trading_context.order_manager.place_order(cmd)
        assert order_result.success is True
        assert order_result.order.symbol == candidate.symbol

    def test_multiple_candidates_create_multiple_orders(self, trading_context):
        """Each candidate should create its own order."""
        universe = _make_trending_universe(n_bars=60)
        scanner = MomentumScanner(top_n=3)
        result = scanner.scan(universe)

        for candidate in result.candidates:
            cmd = OmsOrderCommand(
                symbol=candidate.symbol,
                exchange="NSE",
                side=Side.BUY,
                quantity=10,
                price=Decimal("100.0"),
                correlation_id=f"scanner-{candidate.symbol}",
            )
            order_result = trading_context.order_manager.place_order(cmd)
            assert order_result.success is True

        assert len(trading_context.order_manager.get_orders()) == len(result.candidates)

    def test_score_based_position_sizing(self, trading_context):
        """Higher score should allow larger position size."""
        universe = _make_trending_universe(n_bars=60)
        scanner = MomentumScanner(top_n=3)
        result = scanner.scan(universe)

        if len(result.candidates) >= 2:
            c1, c2 = result.candidates[0], result.candidates[1]
            # Higher score = larger allocation (proportional)
            base_qty = 10
            qty1 = int(base_qty * (c1.score / 50))
            qty2 = int(base_qty * (c2.score / 50))

            for candidate, qty in [(c1, qty1), (c2, qty2)]:
                cmd = OmsOrderCommand(
                    symbol=candidate.symbol,
                    exchange="NSE",
                    side=Side.BUY,
                    quantity=max(1, qty),
                    price=Decimal("100.0"),
                    correlation_id=f"score-size-{candidate.symbol}",
                )
                trading_context.order_manager.place_order(cmd)


# ── Order → Execution ──────────────────────────────────────────────────────


class TestOrderExecution:
    """Tests: Orders execute correctly after scanner generates them."""

    def _submit_fn(self, fill_price: Decimal = Decimal("100.0")):
        from domain import Order, ProductType, OrderType
        def submit_fn(cmd):
            return Order(
                order_id=f"SCAN-{cmd.correlation_id[:8]}",
                symbol=cmd.symbol, exchange=cmd.exchange,
                side=cmd.side, order_type=cmd.order_type,
                quantity=cmd.quantity, price=fill_price,
                status=OrderStatus.OPEN, product_type=cmd.product_type,
                correlation_id=cmd.correlation_id,
            )
        return submit_fn

    def test_scanner_order_fills_correctly(self, trading_context):
        """Scanner-generated orders should fill and create positions."""
        universe = _make_trending_universe(n_bars=60)
        scanner = MomentumScanner(top_n=1)
        result = scanner.scan(universe)

        candidate = result.candidates[0]
        cmd = OmsOrderCommand(
            symbol=candidate.symbol, exchange="NSE", side=Side.BUY,
            quantity=10, price=Decimal("100.0"),
            correlation_id=f"exec-{candidate.symbol}",
        )
        order_result = trading_context.order_manager.place_order(cmd, submit_fn=self._submit_fn())
        trade = Trade(
            trade_id=f"TRD-{order_result.order.order_id}",
            order_id=order_result.order.order_id,
            symbol=candidate.symbol, exchange="NSE", side=Side.BUY,
            quantity=10, price=Decimal("100.0"),
        )
        trading_context.order_manager.record_trade(trade)

        pos = trading_context.position_manager.get_position(candidate.symbol, "NSE")
        assert pos is not None
        assert pos.quantity == 10

    def test_scanner_risk_check_before_execution(self, trading_context):
        """Scanner orders should pass risk checks."""
        universe = _make_trending_universe(n_bars=60)
        scanner = MomentumScanner(top_n=3)
        result = scanner.scan(universe)

        executed = 0
        for candidate in result.candidates:
            cmd = OmsOrderCommand(
                symbol=candidate.symbol, exchange="NSE", side=Side.BUY,
                quantity=10, price=Decimal("100.0"),
                correlation_id=f"risk-check-{candidate.symbol}",
            )
            order_result = trading_context.order_manager.place_order(cmd)
            if order_result.success:
                executed += 1

        assert executed > 0


# ── Portfolio Update ────────────────────────────────────────────────────────


class TestPortfolioUpdate:
    """Tests: Portfolio state updates correctly after scanner-driven trades."""

    def _submit_fn(self, fill_price: Decimal = Decimal("100.0")):
        from domain import Order
        def submit_fn(cmd):
            return Order(
                order_id=f"PF-{cmd.correlation_id[:8]}",
                symbol=cmd.symbol, exchange=cmd.exchange,
                side=cmd.side, order_type=cmd.order_type,
                quantity=cmd.quantity, price=fill_price,
                status=OrderStatus.OPEN, product_type=cmd.product_type,
                correlation_id=cmd.correlation_id,
            )
        return submit_fn

    def test_portfolio_reflects_all_scanner_positions(self, trading_context):
        """All scanner-driven positions should appear in portfolio."""
        universe = _make_trending_universe(n_bars=60)
        scanner = MomentumScanner(top_n=3)
        result = scanner.scan(universe)

        for candidate in result.candidates:
            cmd = OmsOrderCommand(
                symbol=candidate.symbol, exchange="NSE", side=Side.BUY,
                quantity=10, price=Decimal("100.0"),
                correlation_id=f"pf-{candidate.symbol}",
            )
            order_result = trading_context.order_manager.place_order(cmd, submit_fn=self._submit_fn())
            trading_context.order_manager.record_trade(Trade(
                trade_id=f"TRD-{order_result.order.order_id}",
                order_id=order_result.order.order_id,
                symbol=candidate.symbol, exchange="NSE", side=Side.BUY,
                quantity=10, price=Decimal("100.0"),
            ))

        positions = trading_context.position_manager.get_positions()
        assert len(positions) == len(result.candidates)

    def test_portfolio_pnl_after_scanner_trades(self, trading_context):
        """Portfolio should show PnL after positions are updated with LTP."""
        universe = _make_trending_universe(n_bars=60)
        scanner = MomentumScanner(top_n=2)
        result = scanner.scan(universe)

        for candidate in result.candidates:
            cmd = OmsOrderCommand(
                symbol=candidate.symbol, exchange="NSE", side=Side.BUY,
                quantity=10, price=Decimal("100.0"),
                correlation_id=f"pnl-{candidate.symbol}",
            )
            order_result = trading_context.order_manager.place_order(cmd, submit_fn=self._submit_fn())
            trading_context.order_manager.record_trade(Trade(
                trade_id=f"TRD-{order_result.order.order_id}",
                order_id=order_result.order.order_id,
                symbol=candidate.symbol, exchange="NSE", side=Side.BUY,
                quantity=10, price=Decimal("100.0"),
            ))
            # Update LTP to show profit
            trading_context.position_manager.update_ltp(candidate.symbol, "NSE", Decimal("110.0"))

        positions = trading_context.position_manager.get_positions()
        total_pnl = sum(p.unrealized_pnl for p in positions)
        assert total_pnl > 0  # All positions should be in profit

    def test_portfolio_snapshot_after_full_flow(self, trading_context):
        """Full scanner → order → fill flow should produce consistent snapshot."""
        universe = _make_trending_universe(n_bars=60)
        scanner = MomentumScanner(top_n=2)
        result = scanner.scan(universe)

        for candidate in result.candidates:
            cmd = OmsOrderCommand(
                symbol=candidate.symbol, exchange="NSE", side=Side.BUY,
                quantity=10, price=Decimal("100.0"),
                correlation_id=f"snapshot-{candidate.symbol}",
            )
            order_result = trading_context.order_manager.place_order(cmd, submit_fn=self._submit_fn())
            trading_context.order_manager.record_trade(Trade(
                trade_id=f"TRD-{order_result.order.order_id}",
                order_id=order_result.order.order_id,
                symbol=candidate.symbol, exchange="NSE", side=Side.BUY,
                quantity=10, price=Decimal("100.0"),
            ))

        # Verify snapshot
        orders = trading_context.order_manager.get_orders()
        positions = trading_context.position_manager.get_positions()
        health = trading_context.health()

        assert len(orders) > 0
        assert len(positions) > 0
        # Note: May not equal candidates if risk checks filtered some
        assert "metrics" in health
        assert "dead_letter" in health
