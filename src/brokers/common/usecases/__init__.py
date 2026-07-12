"""Broker-agnostic use cases — feature orchestration via BrokerAdapter + strategy."""

from __future__ import annotations

from brokers.common.usecases.depth import DepthStrategy, subscribe_depth
from brokers.common.usecases.exit_all import ExitAllStrategy, exit_all
from brokers.common.usecases.gtt import GttStrategy, cancel_gtt, place_gtt
from brokers.common.usecases.place_bracket import (
    BracketStrategy,
    cancel_bracket,
    place_bracket,
)
from brokers.common.usecases.pnl_exit import PnlExitStrategy, exit_on_pnl

__all__ = [
    "BracketStrategy",
    "DepthStrategy",
    "ExitAllStrategy",
    "GttStrategy",
    "PnlExitStrategy",
    "cancel_bracket",
    "cancel_gtt",
    "exit_all",
    "exit_on_pnl",
    "place_bracket",
    "place_gtt",
    "subscribe_depth",
]
