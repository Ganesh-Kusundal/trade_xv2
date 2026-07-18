"""Supporting transport types for broker gateways.

Product code should prefer the narrow domain ports and the object API::

    session = tradex.connect("dhan")
    equity = session.universe.equity("RELIANCE")
    equity.quote / equity.history(...)     # DataProvider
    session.buy(equity, qty, ...)          # OrderIntent → OMS → ExecutionProvider

Concrete ``*BrokerGateway`` classes under ``brokers/{dhan,upstox,paper}`` are
**transport facades** (ops/CLI/legacy). New strategies and OMS code depend on
:class:`~domain.ports.protocols.DataProvider` and
:class:`~domain.ports.protocols.ExecutionProvider`, not on gateway classes.

Use :class:`~domain.ports.broker_adapter.BrokerAdapter` as the canonical
broker interface.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol, runtime_checkable

from domain.entities import Balance, Order, OrderResponse, Position, Quote, Trade
from domain.entities.market import MarketDepth
from domain.candles.historical import HistoricalBar, InstrumentRef
from domain.orders.requests import ModifyOrderRequest, OrderRequest


# ---------------------------------------------------------------------------
# OrderTransportPort — narrow order-execution protocol
# ---------------------------------------------------------------------------


@runtime_checkable
class OrderTransportPort(Protocol):
    """Narrow order-execution port for the OMS layer.

    Defined here in ``domain.ports.broker_gateway`` so the OMS (and its
    tests) can depend on this protocol without pulling in broker-specific
    transports or the full ``BrokerAdapter``.

    All broker adapters and fake gateways implement this protocol.
    """

    def place_order(
        self,
        symbol: str,
        exchange: str,
        side: str,
        quantity: int,
        **kwargs: str,
    ) -> OrderResponse:
        """Place a single order and return the gateway response."""
        ...


# ---------------------------------------------------------------------------
# Supporting transport types (lifecycle owned by StreamOrchestrator)
# ---------------------------------------------------------------------------


@runtime_checkable
class BrokerStreamHandle(Protocol):
    """Minimal handle returned by open_market_stream / open_order_stream.

    The stream orchestrator holds this handle and uses it to manage connection
    lifecycle.  Consumers never interact with handles directly.
    """

    @property
    def session_id(self) -> str: ...
    @property
    def broker_id(self) -> str: ...
    async def disconnect(self) -> None: ...
    def is_connected(self) -> bool: ...


class BrokerStreamPlan:
    """Input to open_*_stream describing what to subscribe to.

    instruments — set of InstrumentRef strings to subscribe.
    modes       — set of broker-specific stream mode names (e.g. ``{"LTP"}``).
    on_raw_frame — callback invoked by the broker transport for each raw message.
                   The StreamOrchestrator wires its own handler here; callers
                   never set this directly.
    """

    __slots__ = ("instruments", "modes", "on_raw_frame")

    def __init__(
        self,
        instruments: frozenset[str],
        modes: frozenset[str],
        on_raw_frame: object = None,
    ) -> None:
        self.instruments = instruments
        self.modes = modes
        self.on_raw_frame = on_raw_frame


class HistoricalBarRequest:
    """Input to BrokerAdapter.get_historical_bars — a single-broker request.

    The HistoricalDataCoordinator creates these from a larger federated query
    after range clipping and chunking.
    """

    __slots__ = (
        "from_date",
        "instrument",
        "request_id",
        "timeframe",
        "to_date",
    )

    def __init__(
        self,
        instrument: InstrumentRef,
        timeframe: str,
        from_date: str,
        to_date: str,
        request_id: str,
    ) -> None:
        self.instrument = instrument
        self.timeframe = timeframe
        self.from_date = from_date
        self.to_date = to_date
        self.request_id = request_id


class BrokerHealthSnapshot:
    """Point-in-time health view of a single broker gateway.

    alive         — whether the gateway can currently serve requests.
    auth_valid    — whether the current access token is valid.
    error_rate    — recent error rate (0.0-1.0) as observed by health monitor.
    latency_p50   — median API latency in milliseconds.
    reason        — human-readable reason if not alive.
    """

    __slots__ = ("alive", "auth_valid", "broker_id", "error_rate", "latency_p50", "reason")

    def __init__(
        self,
        broker_id: str,
        alive: bool,
        auth_valid: bool = True,
        error_rate: float = 0.0,
        latency_p50: float = 0.0,
        reason: str = "",
    ) -> None:
        self.broker_id = broker_id
        self.alive = alive
        self.auth_valid = auth_valid
        self.error_rate = error_rate
        self.latency_p50 = latency_p50
        self.reason = reason


# ---------------------------------------------------------------------------
# QuotaToken — opaque token issued by QuotaScheduler
# ---------------------------------------------------------------------------


class QuotaToken:
    """Opaque token issued by ``QuotaScheduler.acquire()``.

    Passed into gateway methods to prove the call has been budgeted.
    The scheduler validates tokens at release time for accounting.
    """

    __slots__ = ("_token_id", "broker_id", "endpoint_class", "priority_class")

    def __init__(
        self,
        broker_id: str,
        endpoint_class: str,
        priority_class: str,
        token_id: str,
    ) -> None:
        self.broker_id = broker_id
        self.endpoint_class = endpoint_class
        self.priority_class = priority_class
        self._token_id = token_id

    def __repr__(self) -> str:
        return (
            f"QuotaToken({self.broker_id!r}, {self.endpoint_class!r}, "
            f"{self.priority_class!r}, id={self._token_id!r})"
        )
