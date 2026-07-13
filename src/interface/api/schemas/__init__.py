"""Pydantic schemas for all API request/response types.

Re-exports from sub-modules for backward compatibility.
All existing ``from interface.api.schemas import X`` imports continue to work.
"""

from interface.api.schemas._analytics import (
    IndicatorRequest,
    IndicatorValue,
    IndicatorsResponse,
    MarketBreadthResponse,
    RelativeStrengthResponse,
    ScannerCandidatesResponse,
    ScannerSnapshot,
)
from interface.api.schemas._backtest import (
    BacktestMetrics,
    BacktestResultResponse,
    BacktestRunRequest,
)
from interface.api.schemas._base import (
    APIResponse,
    ErrorDetail,
    ErrorResponse,
    PaginatedResponse,
)
from interface.api.schemas._health import HealthResponse, ReadinessResponse
from interface.api.schemas._market import Candle, CandleRequest, CandlesResponse, QuoteResponse
from interface.api.schemas._options import (
    IVSurfaceResponse,
    MaxPainResponse,
    OptionChainResponse,
    OptionContract,
    PCRResponse,
)
from interface.api.schemas._portfolio import (
    Holding,
    HoldingsResponse,
    OrderListResponse,
    OrderRequest,
    OrderResponse,
    OrdersResponse,
    PortfolioSummary,
    Position,
    PositionListResponse,
    PositionResponse,
    PositionsResponse,
    TradeResponse,
    TradesResponse,
)
from interface.api.schemas._replay import (
    CreateReplaySessionRequest,
    ReplayControlRequest,
    ReplaySessionResponse,
)
from interface.api.schemas._strategy import StrategySignal, StrategySignalsResponse
from interface.api.schemas._symbols import (
    SymbolInfo,
    SymbolSearchRequest,
    SymbolSearchResponse,
    UniverseResponse,
)

__all__ = [
    "APIResponse",
    "BacktestMetrics",
    "BacktestResultResponse",
    "BacktestRunRequest",
    "Candle",
    "CandleRequest",
    "CandlesResponse",
    "CreateReplaySessionRequest",
    "ErrorDetail",
    "ErrorResponse",
    "HealthResponse",
    "Holding",
    "HoldingsResponse",
    "IVSurfaceResponse",
    "IndicatorRequest",
    "IndicatorValue",
    "IndicatorsResponse",
    "MarketBreadthResponse",
    "MaxPainResponse",
    "OptionChainResponse",
    "OptionContract",
    "OrderListResponse",
    "OrderRequest",
    "OrderResponse",
    "OrdersResponse",
    "PCRResponse",
    "PaginatedResponse",
    "PortfolioSummary",
    "Position",
    "PositionListResponse",
    "PositionResponse",
    "PositionsResponse",
    "QuoteResponse",
    "ReadinessResponse",
    "ReplayControlRequest",
    "ReplaySessionResponse",
    "RelativeStrengthResponse",
    "ScannerCandidatesResponse",
    "ScannerSnapshot",
    "StrategySignal",
    "StrategySignalsResponse",
    "SymbolInfo",
    "SymbolSearchRequest",
    "SymbolSearchResponse",
    "TradeResponse",
    "TradesResponse",
    "UniverseResponse",
]
