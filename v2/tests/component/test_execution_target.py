"""Environment → FillSource + Clock matrix (composition-root resolution)."""

from __future__ import annotations

import pytest

from application.execution.fill_sources import (
    BrokerFillSource,
    PaperFillSource,
    ReplayFillSource,
    SimulatedFillSource,
)
from config.schema import Environment
from infrastructure.clock import FakeClock, SystemClock
from runtime.execution_target import resolve_clock, resolve_fill_source

_MATRIX = [
    (Environment.REPLAY, ReplayFillSource, FakeClock),
    (Environment.BACKTEST, SimulatedFillSource, FakeClock),
    (Environment.PAPER, PaperFillSource, SystemClock),
    (Environment.LIVE, BrokerFillSource, SystemClock),
]


@pytest.mark.parametrize(("env", "fill_cls", "clock_cls"), _MATRIX)
def test_resolve_fill_source_and_clock_matrix(
    env: Environment, fill_cls: type, clock_cls: type
) -> None:
    fill = resolve_fill_source(env)
    clock = resolve_clock(env)
    assert isinstance(fill, fill_cls)
    assert isinstance(clock, clock_cls)


def test_live_uses_broker_adapter_when_provided() -> None:
    adapter = object()
    fill = resolve_fill_source(Environment.LIVE, broker_adapter=adapter)
    assert isinstance(fill, BrokerFillSource)
    assert fill._adapter is adapter  # noqa: SLF001


def test_paper_uses_gateway_when_provided() -> None:
    gateway = object()
    fill = resolve_fill_source(Environment.PAPER, broker_adapter=gateway)
    assert isinstance(fill, PaperFillSource)
    assert fill._gateway is gateway  # noqa: SLF001
