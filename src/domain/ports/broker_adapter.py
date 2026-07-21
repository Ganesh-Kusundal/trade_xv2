"""BrokerAdapter — unified broker adapter abstract base class (composition root).

Phase 9.1 of the Instrument-Centric SDK Redesign.

This is the composition-root contract that unifies market-data access and
order execution behind a single interface.  A ``BrokerAdapter`` is a class
with ``broker_id``, ``is_connected``, ``authenticate()``, ``close()``, and
the union of :class:`DataProvider` and :class:`ExecutionProvider` methods.

Unlike structural Protocol conformance, this ABC enforces **nominal typing**
via ``@abstractmethod`` — any class that does not implement every required
method will fail at class instantiation time, not at call time.

For example::

    from domain.ports.broker_adapter import BrokerAdapter

    class MyBroker(BrokerAdapter):
        broker_id = "my_broker"
        @property
        def is_connected(self) -> bool: ...
        def authenticate(self) -> bool: ...
        def close(self) -> None: ...
        def quote(self, symbol, exchange) -> Quote: ...
        # ... all @abstractmethod must be implemented

Every concrete broker (``DhanWireAdapter``, ``UpstoxWireAdapter``,
``PaperGateway``) is now a nominal subclass of ``BrokerAdapter``.

Interface Segregation
---------------------
``BrokerAdapter`` composes three focused sub-ports:

* :class:`BrokerMarketDataPort` — read-only market data operations
* :class:`BrokerExecutionPort` — order execution operations
* :class:`BrokerStreamingPort` — live streaming operations

Callers that only need a subset of capabilities should depend on the
narrower port (e.g. scanners depend on ``BrokerMarketDataPort``; OMS
depends on ``BrokerExecutionPort``).

Instrument loading & security mapping
-------------------------------------
Instrument master loading and symbol→broker-native-identifier mapping
(Dhan ``security_id``, Upstox ``instrument_key``, segment codes) are
**internal to each broker**. Gateways must only pass canonical
``(symbol, exchange)`` and receive canonical domain objects
(``Quote``, ``MarketDepth``, …). Wire identifiers must never leak into
gateway method signatures or return values.

Every broker implements :class:`brokers.common.instruments.BrokerInstrumentService`
behind its connection / broker facade:

* ``load_instruments()`` / ``load()`` — populate the in-memory resolver
* ``is_loaded()`` — gate subscriptions when the master is empty
* ``resolve_ref()`` — opaque wire ref consumed only by the connection

This is a pure domain port: it contains no broker-specific logic, no
implementation, and imports nothing from ``brokers.*`` or ``providers.*``.
"""

from __future__ import annotations

from abc import ABC
from typing import TYPE_CHECKING

from domain.ports.broker_execution_port import BrokerExecutionPort
from domain.ports.broker_market_data_port import BrokerMarketDataPort
from domain.ports.broker_streaming_port import BrokerStreamingPort
from domain.ports.protocols import DataProvider, ExecutionProvider

if TYPE_CHECKING:
    pass  # DepthStreamHandle lives in brokers.common.streaming (outer layer)


class BrokerAdapter(
    BrokerMarketDataPort,
    BrokerExecutionPort,
    BrokerStreamingPort,
    DataProvider,
    ExecutionProvider,
    ABC,
):
    """Unified broker interface: data + execution + streaming in one object.

    Composes three focused sub-ports:

    * :class:`BrokerMarketDataPort` — read-only market data (quote, ltp, depth,
      history, option_chain, future_chain, search, capabilities, instruments)
    * :class:`BrokerExecutionPort` — order operations (place, cancel, modify,
      orderbook, tradebook, positions, holdings, funds)
    * :class:`BrokerStreamingPort` — live feeds (stream, unstream, stream_depth,
      stream_order)

    Callers that only need a subset of capabilities should depend on the
    narrower port instead of the full ``BrokerAdapter``.
    """

    # NOTE: ``trades()`` is intentionally NOT an abstract method. Every
    # concrete wire adapter inherits it from ``BaseWireAdapter``, which
    # delegates consistently to ``get_trade_book()``.
