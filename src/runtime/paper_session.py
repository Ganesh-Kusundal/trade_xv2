"""Runtime-owned paper session composer (ADR-0012).

Single entry for operator-facing PARITY paths: backtest, replay, paper CLI/API.
"""

from __future__ import annotations

import tempfile
from collections.abc import Callable
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from typing import Any

from application.execution.execution_engine import ExecutionEngine
from application.execution.oms_backtest_adapter import (
    OmsBacktestAdapter,
    create_oms_backtest_adapter,
)
from application.oms.context import TradingContext
from application.oms.factory import create_trading_context
from application.oms._internal.risk_manager import RiskConfig, RiskManager
from application.oms.capital_provider import FixedCapitalProvider, resolve_capital_provider
from application.oms.position_manager import PositionManager
from domain.constants.defaults import PAPER_INITIAL_CAPITAL
from domain.ports.execution_target import ExecutionTargetKind
from infrastructure.event_bus import EventBus, ProcessedTradeRepository, create_default_dead_letter_queue
from infrastructure.event_log import BufferedEventLog
from runtime.execution_config import resolve_execution_target_kind
from runtime.execution_target import resolve_execution_target


@dataclass(frozen=True)
class PaperSession:
    """Wired paper/backtest/replay session — OMS is SSOT."""

    trading_context: TradingContext
    execution_engine: ExecutionEngine
    oms_adapter: OmsBacktestAdapter
    execution_kind: ExecutionTargetKind
    initial_capital: Decimal
    research_only: bool = False


def _quote_from_gateway(gateway: Any) -> Callable[[str, str], Decimal]:
    from domain.exceptions import QuoteUnavailableError

    def _quote(symbol: str, exchange: str) -> Decimal:
        if gateway is None:
            raise QuoteUnavailableError("no gateway for quote resolution")
        try:
            q = gateway.quote(symbol, exchange)
            return Decimal(str(q.ltp))
        except Exception:
            try:
                return Decimal(str(gateway.ltp(symbol, exchange)))
            except Exception as exc2:
                raise QuoteUnavailableError(
                    f"quote unavailable for {symbol}/{exchange}"
                ) from exc2

    return _quote


def build_paper_session(
    *,
    initial_capital: float | Decimal | None = None,
    execution_kind: ExecutionTargetKind | str | None = None,
    gateway: Any | None = None,
    quote_fn: Callable[[str, str], Decimal] | None = None,
    slippage_pct: float = 0.0,
    commission_flat: float = 0.0,
    events_dir: Path | None = None,
) -> PaperSession:
    """Compose TradingContext + PAPER target + ExecutionEngine + OmsBacktestAdapter."""
    from runtime.kernel import ProcessKernel

    ProcessKernel.wire()
    capital = Decimal(str(initial_capital or PAPER_INITIAL_CAPITAL))
    kind = resolve_execution_target_kind(execution_kind or ExecutionTargetKind.PAPER)

    dlq = create_default_dead_letter_queue()
    event_dir = events_dir or Path(tempfile.mkdtemp(prefix="tradex-paper-events-"))
    event_bus = EventBus(dead_letter_queue=dlq)
    processed_trades = ProcessedTradeRepository()
    event_log = BufferedEventLog(events_dir=event_dir)

    position_manager = PositionManager(
        event_bus=event_bus,
        processed_trade_repository=processed_trades,
    )
    capital_provider = resolve_capital_provider(
        execution_kind=kind,
        gateway=gateway,
        fixed_capital=capital,
    )
    risk_manager = RiskManager(
        position_manager=position_manager,
        config=RiskConfig(),
        capital_provider=capital_provider,
    )

    trading_context = create_trading_context(
        risk_manager=risk_manager,
        position_manager=position_manager,
        capital_fn=lambda: capital,
        event_bus=event_bus,
        dead_letter_queue=dlq,
        processed_trade_repository=processed_trades,
        event_log=event_log,
        replay_events=True,
    )

    resolved_quote = quote_fn or (_quote_from_gateway(gateway) if gateway else None)
    target = resolve_execution_target(
        kind,
        gateway=gateway if kind is ExecutionTargetKind.LIVE else None,
        order_id_prefix="paper" if kind is ExecutionTargetKind.PAPER else "bt",
        quote_fn=resolved_quote,
    )
    execution_engine = ExecutionEngine(target, trading_context)
    oms_adapter = create_oms_backtest_adapter(
        trading_context,
        mode=kind.value,
        slippage_pct=slippage_pct,
        commission_flat=commission_flat,
        execution_adapter=None,
    )

    return PaperSession(
        trading_context=trading_context,
        execution_engine=execution_engine,
        oms_adapter=oms_adapter,
        execution_kind=kind,
        initial_capital=capital,
        research_only=False,
    )


def build_backtest_engine(
    pipeline,
    strategy_pipeline,
    config,
    *,
    research_only: bool = False,
    **session_kwargs,
):
    """Operator-facing BacktestEngine — PARITY default, ``research_only`` for PURE_SIM."""
    from analytics.backtest import BacktestConfig, BacktestEngine, ResearchMode

    config = config or BacktestConfig()

    if research_only:
        return BacktestEngine(
            pipeline,
            strategy_pipeline,
            config,
            mode=ResearchMode.PURE_SIM,
        )
    session = build_paper_session(
        initial_capital=config.initial_capital,
        slippage_pct=getattr(config, "slippage_pct", 0.0),
        commission_flat=getattr(config, "commission_flat", 0.0),
        **session_kwargs,
    )
    return BacktestEngine(
        pipeline,
        strategy_pipeline,
        config,
        mode=ResearchMode.PARITY,
        trading_context=session.trading_context,
        oms_adapter=session.oms_adapter,
    )


def build_replay_engine(
    pipeline,
    strategy_pipeline,
    config,
    *,
    research_only: bool = False,
    **session_kwargs,
):
    """Operator-facing ReplayEngine — PARITY default, ``research_only`` for PURE_SIM."""
    from analytics.replay import ReplayEngine

    if research_only:
        return ReplayEngine(
            pipeline,
            strategy_pipeline,
            config,
            allow_simulate_without_oms=True,
        )
    session = build_paper_session(
        initial_capital=config.initial_capital,
        execution_kind=ExecutionTargetKind.REPLAY,
        slippage_pct=getattr(config, "slippage_pct", 0.0),
        commission_flat=getattr(config, "commission_flat", 0.0),
        **session_kwargs,
    )
    return ReplayEngine(
        pipeline,
        strategy_pipeline,
        config,
        trading_context=session.trading_context,
        oms_adapter=session.oms_adapter,
    )


def build_paper_trading_engine(
    pipeline,
    strategy_pipeline,
    config,
    *,
    research_only: bool = False,
    **session_kwargs,
):
    """Operator-facing PaperTradingEngine — PARITY default."""
    from analytics.paper import PaperTradingEngine

    if research_only:
        return PaperTradingEngine(
            pipeline,
            strategy_pipeline,
            config,
            allow_simulate_without_oms=True,
        )
    session = build_paper_session(
        initial_capital=config.initial_capital,
        slippage_pct=getattr(config, "slippage_pct", 0.0),
        commission_flat=getattr(config, "commission_flat", 0.0),
        **session_kwargs,
    )
    return PaperTradingEngine(
        pipeline,
        strategy_pipeline,
        config,
        trading_context=session.trading_context,
        oms_adapter=session.oms_adapter,
    )


__all__ = [
    "PaperSession",
    "build_paper_session",
    "build_backtest_engine",
    "build_replay_engine",
    "build_paper_trading_engine",
]
