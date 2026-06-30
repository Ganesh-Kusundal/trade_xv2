"""Fake implementations for trading orchestration interfaces."""

from __future__ import annotations

from dataclasses import dataclass

from application.oms.protocols import ITradingOrchestrator


@dataclass
class FakeTradingOrchestrator(ITradingOrchestrator):
    """Fake trading orchestrator for lifecycle testing.

    Instead of mocking the orchestrator:

        # BEFORE:
        mock_orch = MagicMock()
        mock_orch.name = "test_orchestrator"

        # AFTER:
        fake_orch = FakeTradingOrchestrator()
        fake_orch.start()
        assert fake_orch.started
    """

    name: str = "fake_orchestrator"
    started: bool = False
    stopped: bool = False
    stop_timeout: float | None = None
    start_calls: int = 0
    stop_calls: int = 0

    def start(self) -> None:
        """Start the fake orchestrator."""
        self.started = True
        self.stopped = False
        self.start_calls += 1

    def stop(self, timeout_seconds: float = 30.0) -> None:
        """Stop the fake orchestrator."""
        self.stopped = True
        self.stop_timeout = timeout_seconds
        self.stop_calls += 1
