"""StreamOrchestrator gap-reconciled bar injection."""

from __future__ import annotations

from datetime import datetime, timezone

from application.streaming.orchestrator import StreamOrchestrator


def test_inject_reconciled_bars_invokes_handler() -> None:
    received: list[tuple[str, int]] = []

    def handler(bar) -> None:
        received.append((bar.symbol, int(bar.volume)))

    orch = StreamOrchestrator(registry=None, router=None)
    orch.attach_reconciled_bar_handler(handler)
    ts = datetime(2026, 1, 1, 10, 0, tzinfo=timezone.utc).isoformat()
    orch.inject_reconciled_bars(
        "RELIANCE:NSE",
        [
            {
                "symbol": "RELIANCE",
                "exchange": "NSE",
                "timestamp": ts,
                "open": 100,
                "high": 102,
                "low": 99,
                "close": 101,
                "volume": 1200,
            }
        ],
    )
    assert received == [("RELIANCE", 1200)]
