"""Fake implementations for trading orchestration."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class FakeTradingOrchestrator:
    """Fake trading orchestrator for lifecycle testing."""

    name: str = "fake_orchestrator"
    started: bool = False
    stopped: bool = False
    stop_timeout: float | None = None
    start_calls: int = 0
    stop_calls: int = 0

    def start(self) -> None:
        self.started = True
        self.stopped = False
        self.start_calls += 1

    def stop(self, timeout_seconds: float = 30.0) -> None:
        self.stopped = True
        self.stop_timeout = timeout_seconds
        self.stop_calls += 1
