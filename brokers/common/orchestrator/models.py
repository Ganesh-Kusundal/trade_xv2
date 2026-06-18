"""Trading orchestrator models — ExecutionRequest, ExecutionResult, FeatureFetcher.

This module defines the data structures and protocols used by the TradingOrchestrator
to connect the Scanner→Strategy→OMS execution path.

The orchestrator:
1. Subscribes to CANDIDATE_GENERATED events from the EventBus
2. Fetches feature data for each candidate via FeatureFetcher
3. Evaluates candidates through StrategyPipeline
4. Converts actionable signals to OmsOrderCommand
5. Places orders through OrderManager
6. Publishes RISK_APPROVED/RISK_REJECTED events based on OMS result
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Protocol, runtime_checkable

import pandas as pd

from analytics.scanner.models import Candidate
from analytics.strategy.models import Signal


@dataclass(frozen=True)
class ExecutionRequest:
    """Request to execute a signal through the OMS.
    
    This is the bridge between the strategy layer (Signal) and the
    execution layer (OmsOrderCommand). It carries all information
    needed to place an order, including correlation tracking for
    audit and replay purposes.
    
    Attributes
    ----------
    signal:
        The actionable signal from strategy evaluation.
    correlation_id:
        Unique identifier linking this execution request to the
        original candidate and any subsequent orders/fills.
    timestamp:
        UTC timestamp when the execution request was created.
    """
    
    signal: Signal
    correlation_id: str
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass
class ExecutionResult:
    """Result of executing a signal through the OMS.
    
    Attributes
    ----------
    success:
        True if the order was successfully placed.
    order_id:
        The OMS order ID if successful.
    error:
        Error message if the execution failed.
    signal:
        The original signal that was executed (for audit trail).
    """
    
    success: bool
    order_id: str | None = None
    error: str | None = None
    signal: Signal | None = None


@runtime_checkable
class FeatureFetcher(Protocol):
    """Protocol for fetching feature data for a symbol.
    
    The orchestrator uses this protocol to decouple feature fetching
    from strategy evaluation. This allows different implementations:
    
    - LiveFeatureFetcher: Fetches real-time features from data pipeline
    - CachedFeatureFetcher: Fetches from in-memory cache with TTL
    - BacktestFeatureFetcher: Fetches historical features from datalake
    
    Usage:
        fetcher = LiveFeatureFetcher(pipeline)
        features = fetcher.fetch("RELIANCE")
        if features is not None:
            signal = strategy.evaluate_single(candidate, features)
    """
    
    def fetch(self, symbol: str) -> pd.DataFrame | None:
        """Fetch feature data for a symbol.
        
        Parameters
        ----------
        symbol:
            NSE/BSE symbol (e.g. "RELIANCE").
            
        Returns
        -------
        pd.DataFrame | None:
            DataFrame with feature columns, or None if features
            cannot be fetched (symbol not found, data unavailable, etc.).
        """
        ...


__all__ = [
    "ExecutionRequest",
    "ExecutionResult",
    "FeatureFetcher",
]
