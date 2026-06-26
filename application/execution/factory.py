"""Factory helpers for execution wiring (composition root)."""

from __future__ import annotations

from decimal import Decimal
from application.oms.context import TradingContext

from application.execution.execution_mode_adapter import create_execution_adapter
from application.execution.oms_backtest_adapter import OmsBacktestAdapter
from application.oms.protocols import IExecutionAdapter


def create_oms_backtest_adapter(
    trading_context: TradingContext,
    *,
    mode: str = "replay",
    slippage_pct: float = 0.0,
    commission_flat: float = 0.0,
    execution_adapter: IExecutionAdapter | None = None,
) -> OmsBacktestAdapter:
    """Build an OMS backtest adapter for paper/replay engines."""
    adapter = execution_adapter or create_execution_adapter(mode, trading_context)
    return OmsBacktestAdapter(
        trading_context=trading_context,
        slippage_pct=slippage_pct,
        commission_flat=Decimal(str(commission_flat)),
        execution_adapter=adapter,
    )


__all__ = ["create_oms_backtest_adapter"]
