"""Execution target resolution — FillSource + Clock by Environment (sole mode branch)."""

from __future__ import annotations

from typing import Any

from application.execution.fill_sources import (
    BrokerFillSource,
    PaperFillSource,
    ReplayFillSource,
    SimulatedFillSource,
)
from application.execution.protocols import FillSource
from config.schema import Environment
from infrastructure.clock import FakeClock, SystemClock


def _env(environment: Environment | str) -> Environment:
    if isinstance(environment, Environment):
        return environment
    return Environment(str(environment))


def resolve_fill_source(
    environment: Environment | str,
    broker_adapter: Any | None = None,
) -> FillSource:
    """Map Environment → Simulated | Paper | Broker | Replay FillSource."""
    env = _env(environment)
    if env is Environment.BACKTEST:
        return SimulatedFillSource()
    if env is Environment.PAPER:
        return PaperFillSource(gateway=broker_adapter)
    if env is Environment.LIVE:
        return BrokerFillSource(adapter=broker_adapter)
    if env is Environment.REPLAY:
        return ReplayFillSource()
    msg = f"unsupported environment: {env!r}"
    raise ValueError(msg)


def resolve_clock(environment: Environment | str) -> SystemClock | FakeClock:
    """REPLAY/BACKTEST → FakeClock; PAPER/LIVE → SystemClock."""
    env = _env(environment)
    if env in (Environment.REPLAY, Environment.BACKTEST):
        return FakeClock()
    if env in (Environment.PAPER, Environment.LIVE):
        return SystemClock()
    msg = f"unsupported environment: {env!r}"
    raise ValueError(msg)
