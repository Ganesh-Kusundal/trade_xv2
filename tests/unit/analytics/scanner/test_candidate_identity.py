"""Scanner candidate identity and event correlation."""

from __future__ import annotations

from decimal import Decimal
from unittest.mock import MagicMock

import pandas as pd

from analytics.scanner.scanners import MomentumScanner
from application.trading.trading_orchestrator import TradingOrchestrator
from domain.events.types import DomainEvent, EventType


def test_scanner_publishes_deterministic_candidate_id():
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
    assert bus.publish.called
    candidate_payloads = []
    for call in bus.publish.call_args_list:
        event_type = call.args[0] if call.args else call.kwargs.get("event_type")
        payload = call.kwargs.get("payload")
        if event_type == EventType.CANDIDATE_GENERATED.value and payload:
            candidate_payloads.append(payload)
    assert candidate_payloads, "expected at least one CANDIDATE_GENERATED event"
    payload = candidate_payloads[0]
    assert payload["candidate_id"].startswith("momentum:NSE:AAA:")
    assert payload["exchange"] == "NSE"


def test_orchestrator_uses_candidate_id_not_none_strategy():
    from application.trading.execution_planner import ExecutionPlanner
    from domain import OrderType, ProductType
    from domain.models.trading import SignalDTO

    planner = ExecutionPlanner(
        min_confidence=0.7,
        default_exchange="NSE",
        default_order_type=OrderType.MARKET,
        default_product_type=ProductType.INTRADAY,
    )

    signal = SignalDTO(
        symbol="RELIANCE",
        exchange="NSE",
        side="BUY",
        signal_type="BUY",
        strategy="momentum",
        confidence=Decimal("0.8"),
        entry_price=Decimal("2500"),
        quantity=1,
    )
    cmd = planner.signal_to_order_command(signal, "momentum:NSE:RELIANCE:scan-1")
    assert cmd.correlation_id == "momentum:NSE:RELIANCE:scan-1:momentum"
    assert "None" not in cmd.correlation_id


def test_event_bus_adapter_forwards_candidate_id_as_correlation():
    from infrastructure.event_bus.domain_bus_adapter import InfrastructureEventBusAdapter

    inner = MagicMock()
    adapter = InfrastructureEventBusAdapter(inner)
    adapter.publish(
        EventType.CANDIDATE_GENERATED.value,
        {
            "symbol": "TCS",
            "candidate_id": "momentum:NSE:TCS:abc123",
            "score": 80,
        },
    )
    event = inner.publish.call_args[0][0]
    assert event.correlation_id == "momentum:NSE:TCS:abc123"
    assert event.symbol == "TCS"