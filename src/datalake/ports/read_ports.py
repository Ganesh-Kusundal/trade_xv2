"""Read port protocols for DataLakeGateway decomposition."""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class HistoryReadPort(Protocol):
    """Point-in-time and range historical OHLCV reads."""

    def history(self, symbol: str, *args: Any, **kwargs: Any) -> Any: ...
    def query_candles(self, *args: Any, **kwargs: Any) -> Any: ...


@runtime_checkable
class BatchReadPort(Protocol):
    """Parallel batch reads."""

    def history_batch(self, *args: Any, **kwargs: Any) -> Any: ...
    def quote_batch(self, *args: Any, **kwargs: Any) -> Any: ...
    def ltp_batch(self, *args: Any, **kwargs: Any) -> Any: ...


@runtime_checkable
class OptionsChainPort(Protocol):
    """Derivatives chain reads."""

    def option_chain(self, *args: Any, **kwargs: Any) -> Any: ...
    def future_chain(self, *args: Any, **kwargs: Any) -> Any: ...
