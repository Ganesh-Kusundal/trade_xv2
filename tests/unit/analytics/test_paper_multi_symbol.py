"""Tests for multi-symbol chronological processing in PaperTradingEngine."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock

import pandas as pd
import pytest

from analytics.paper.engine import PaperTradingEngine
from analytics.paper.models import PaperConfig, PaperPosition, PositionSide
from analytics.pipeline.pipeline import FeaturePipeline


@pytest.fixture
def mock_oms_adapter():
    adapter = MagicMock()
    adapter.open_long.return_value = "mock-order-001"
    adapter.close_long.return_value = "mock-order-002"
    return adapter


def _pipeline():
    from analytics.pipeline import ATR, RSI, SMA

    return FeaturePipeline().add(RSI(14)).add(ATR(14)).add(SMA(20))


def _interleaved_multi_df():
    """Two symbols with alternating timestamps (BBB first, then AAA, etc.)."""
    t0 = datetime(2026, 1, 1, 10, 0, tzinfo=timezone.utc)
    timestamps = [
        t0,
        t0 + timedelta(minutes=1),
        t0 + timedelta(minutes=2),
        t0 + timedelta(minutes=3),
    ]
    symbols = ["BBB", "AAA", "BBB", "AAA"]
    return pd.DataFrame(
        {
            "timestamp": timestamps,
            "symbol": symbols,
            "open": [10.0, 20.0, 11.0, 21.0],
            "high": [10.5, 20.5, 11.5, 21.5],
            "low": [9.5, 19.5, 10.5, 20.5],
            "close": [10.0, 20.0, 11.0, 21.0],
            "volume": [1000.0] * 4,
        }
    )


class TestPaperMultiSymbolChronological:
    def test_processes_bars_in_timestamp_order(self, mock_oms_adapter):
        df = _interleaved_multi_df()
        processed_order: list[tuple[str, datetime]] = []
        original_check_exits = PaperTradingEngine._check_exits

        def tracking_check_exits(self, bar, session):
            processed_order.append((bar.symbol, bar.timestamp))
            return original_check_exits(self, bar, session)

        engine = PaperTradingEngine(
            _pipeline(),
            config=PaperConfig(warmup_bars=0),
            oms_adapter=mock_oms_adapter,
        )
        engine._check_exits = tracking_check_exits.__get__(engine, PaperTradingEngine)
        engine.run(df)

        expected = list(zip(df["symbol"], df["timestamp"]))
        assert processed_order == expected

    def test_close_uses_each_symbol_last_bar_price(self, mock_oms_adapter):
        t0 = datetime(2026, 1, 1, tzinfo=timezone.utc)
        df = pd.DataFrame(
            {
                "timestamp": [
                    t0,
                    t0 + timedelta(hours=1),
                    t0 + timedelta(hours=2),
                    t0 + timedelta(hours=3),
                ],
                "symbol": ["AAA", "BBB", "AAA", "BBB"],
                "open": [100.0, 200.0, 100.0, 200.0],
                "high": [100.0, 200.0, 100.0, 200.0],
                "low": [100.0, 200.0, 100.0, 200.0],
                "close": [100.0, 200.0, 150.0, 250.0],
                "volume": [1000.0] * 4,
            }
        )

        engine = PaperTradingEngine(
            _pipeline(),
            config=PaperConfig(
                warmup_bars=0,
                slippage_pct=0.0,
                commission_pct=0.0,
                commission_flat=0.0,
            ),
            oms_adapter=mock_oms_adapter,
        )

        def seed_positions(self, bars, session):
            for _ in bars:
                session.bar_count += 1
            session.bootstrap_position(
                PaperPosition(
                    symbol="AAA",
                    side=PositionSide.LONG,
                    entry_price=100.0,
                    quantity=10,
                    entry_time=t0,
                    current_price=100.0,
                )
            )
            session.bootstrap_position(
                PaperPosition(
                    symbol="BBB",
                    side=PositionSide.LONG,
                    entry_price=200.0,
                    quantity=10,
                    entry_time=t0 + timedelta(hours=1),
                    current_price=200.0,
                )
            )
            return []

        engine._process_bar_stream = seed_positions.__get__(engine, PaperTradingEngine)
        result = engine._run_multi_symbol(
            df.sort_values("timestamp").reset_index(drop=True),
            "timestamp",
        )

        assert len(result.session.trades) == 2
        by_sym = {trade.symbol: trade for trade in result.session.trades}
        assert by_sym["AAA"].exit_price == pytest.approx(150.0)
        assert by_sym["BBB"].exit_price == pytest.approx(250.0)