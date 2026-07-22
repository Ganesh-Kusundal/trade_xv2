"""Architecture ratchet — research scanner/backtest engines (Phase 4 R13)."""

from __future__ import annotations

import ast
import inspect
from unittest.mock import MagicMock

import pandas as pd
import pytest

from analytics.backtest.fast_backtest import FastBacktestEngine
from analytics.backtest.models import CapitalMetricsLabel
from analytics.pipeline.pipeline import FeaturePipeline
from analytics.replay.models import SimulatedTrade
from analytics.scanner.models import BaseScanner
from analytics.scanner.scanners import MomentumScanner
from analytics.strategy.pipeline import StrategyPipeline
from domain.events.types import EventType


def _method_body_without_docstring(class_src: str, method_name: str) -> ast.AST | None:
    tree = ast.parse(class_src)
    class_node = tree.body[0] if tree.body else None
    if not isinstance(class_node, ast.ClassDef):
        return None
    for node in class_node.body:
        if isinstance(node, ast.FunctionDef) and node.name == method_name:
            body = list(node.body)
            if body and isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant):
                body = body[1:]
            return ast.Module(body=body, type_ignores=[])
    return None


@pytest.mark.architecture
def test_base_scanner_exposes_begin_finish_helpers() -> None:
    for name in ("_begin_scan", "_finish_scan", "_empty_scan_result"):
        assert hasattr(BaseScanner, name), f"BaseScanner missing {name}"


@pytest.mark.architecture
def test_base_scanner_scan_does_not_publish_before_not_implemented() -> None:
    body = _method_body_without_docstring(inspect.getsource(BaseScanner), "scan")
    assert body is not None
    src = ast.unparse(body)
    assert "event_bus.publish" not in src
    assert "SCAN_STARTED" not in src
    assert "NotImplementedError" in src


@pytest.mark.architecture
def test_base_scanner_scan_does_not_orphan_scan_started() -> None:
    bus = MagicMock()
    scanner = BaseScanner(pipeline=FeaturePipeline(), event_bus=bus)
    with pytest.raises(NotImplementedError):
        scanner.scan(pd.DataFrame())
    bus.publish.assert_not_called()


@pytest.mark.architecture
def test_scanner_scan_events_pair_on_success() -> None:
    bus = MagicMock()
    scanner = MomentumScanner(event_bus=bus, top_n=1)
    n = 30
    dates = pd.date_range("2026-01-01", periods=n, freq="D")
    close = 100 + pd.Series(range(n), dtype=float)
    df = pd.DataFrame(
        {
            "symbol": ["AAA"] * n,
            "timestamp": dates,
            "open": close - 1,
            "high": close + 2,
            "low": close - 2,
            "close": close,
            "volume": 1_000_000,
        }
    )
    scanner.scan(df)
    event_types = [call.args[0] for call in bus.publish.call_args_list]
    assert event_types.count(EventType.SCAN_STARTED.value) == 1
    assert event_types.count(EventType.SCAN_COMPLETED.value) == 1
    assert EventType.CANDIDATE_GENERATED.value in event_types
    assert event_types.index(EventType.SCAN_STARTED.value) < event_types.index(
        EventType.SCAN_COMPLETED.value
    )


@pytest.mark.architecture
def test_scanner_scan_events_pair_on_empty_universe() -> None:
    bus = MagicMock()
    scanner = MomentumScanner(event_bus=bus)
    scanner.scan(pd.DataFrame())
    event_types = [call.args[0] for call in bus.publish.call_args_list]
    assert event_types == [
        EventType.SCAN_STARTED.value,
        EventType.SCAN_COMPLETED.value,
    ]


@pytest.mark.architecture
def test_fast_backtest_research_label_and_session_trade_typing() -> None:
    engine = FastBacktestEngine(FeaturePipeline(), StrategyPipeline())
    empty = pd.DataFrame(columns=["timestamp", "open", "high", "low", "close", "volume"])
    result = engine.run(empty)
    assert result.capital_metrics_label is CapitalMetricsLabel.RESEARCH
    assert result.capital_metrics_valid is False
    assert isinstance(result.replay.session.trades, list)
    assert result.replay.session.trades == []
    assert all(isinstance(t, SimulatedTrade) for t in result.replay.session.trades)


@pytest.mark.architecture
def test_fast_backtest_does_not_assign_domain_trades_to_session() -> None:
    src = inspect.getsource(FastBacktestEngine.run)
    assert "session.trades = trades" not in src.replace(" ", "")
