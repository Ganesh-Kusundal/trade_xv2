from __future__ import annotations

"""Unified Upstox BrokerAdapter (data + execution + lifecycle).

Phase 9.2 of the Instrument-Centric SDK Redesign.

Combines Upstox's ``DataProvider`` and ``ExecutionProvider`` behind the single
:class:`BrokerAdapter` protocol. Construction is delegated to the
composition-root factory so all broker wiring stays in one place and this
module never imports the broker gateway directly.
"""

from typing import Any

from brokers.common.adapter_factory import (
    create_data_adapter,
    create_execution_provider,
)


class UpstoxBrokerAdapter:
    """Unified Upstox broker adapter: market data + order execution + lifecycle."""

    broker_id: str = "upstox"
    is_connected: bool = True

    def __init__(self, gateway: Any, *, broker_id: str = "upstox") -> None:
        self._data = create_data_adapter(gateway, broker_id=broker_id)
        self._exec = create_execution_provider(gateway, broker_id=broker_id)
        self.broker_id = broker_id

    # ── DataProvider port (delegated to self._data) ──────────────

    @property
    def name(self) -> str:
        return self._data.name

    def get_quote(self, *args: Any, **kwargs: Any) -> Any:
        return self._data.get_quote(*args, **kwargs)

    def get_history(self, *args: Any, **kwargs: Any) -> Any:
        return self._data.get_history(*args, **kwargs)

    def get_history_series(self, *args: Any, **kwargs: Any) -> Any:
        return self._data.get_history_series(*args, **kwargs)

    def get_depth(self, *args: Any, **kwargs: Any) -> Any:
        return self._data.get_depth(*args, **kwargs)

    def get_option_chain(self, *args: Any, **kwargs: Any) -> Any:
        return self._data.get_option_chain(*args, **kwargs)

    def get_future_chain(self, *args: Any, **kwargs: Any) -> Any:
        return self._data.get_future_chain(*args, **kwargs)

    def subscribe(self, *args: Any, **kwargs: Any) -> Any:
        return self._data.subscribe(*args, **kwargs)

    def unsubscribe(self, *args: Any, **kwargs: Any) -> Any:
        return self._data.unsubscribe(*args, **kwargs)

    def history_batch(self, *args: Any, **kwargs: Any) -> Any:
        return self._data.history_batch(*args, **kwargs)

    def list_instruments(self, *args: Any, **kwargs: Any) -> Any:
        return self._data.list_instruments(*args, **kwargs)

    def get_quotes_batch(self, *args: Any, **kwargs: Any) -> Any:
        return self._data.get_quotes_batch(*args, **kwargs)

    # ── ExecutionProvider port (delegated to self._exec; None-safe) ─

    def place_order(self, *args: Any, **kwargs: Any) -> Any:
        if self._exec is None:
            return None
        return self._exec.place_order(*args, **kwargs)

    def cancel_order(self, *args: Any, **kwargs: Any) -> Any:
        if self._exec is None:
            return None
        return self._exec.cancel_order(*args, **kwargs)

    def modify_order(self, *args: Any, **kwargs: Any) -> Any:
        if self._exec is None:
            return None
        return self._exec.modify_order(*args, **kwargs)

    def get_order_book(self, *args: Any, **kwargs: Any) -> Any:
        if self._exec is None:
            return None
        return self._exec.get_order_book(*args, **kwargs)

    def get_positions(self, *args: Any, **kwargs: Any) -> Any:
        if self._exec is None:
            return None
        return self._exec.get_positions(*args, **kwargs)

    def get_holdings(self, *args: Any, **kwargs: Any) -> Any:
        if self._exec is None:
            return None
        return self._exec.get_holdings(*args, **kwargs)

    def get_funds(self, *args: Any, **kwargs: Any) -> Any:
        if self._exec is None:
            return None
        return self._exec.get_funds(*args, **kwargs)

    # ── Connection lifecycle ─────────────────────────────────────

    def authenticate(self) -> bool:
        """Upstox adapters are pre-authenticated at the gateway layer."""
        return True

    def close(self) -> None:
        """No-op: underlying gateway owns its connection lifecycle."""
        pass
