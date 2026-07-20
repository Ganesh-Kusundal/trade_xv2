"""Shared streaming-subscription handle for gateway-level depth/tick streams.

Wraps a :class:`~domain.ports.broker_stream_gateway.BrokerStreamGateway` stop
hook when provided. Matches the ad-hoc handle convention already used by Upstox's
``LtpStreamHandle``/``OrderStreamHandle``/``DepthStreamHandle`` in
``brokers/upstox/adapters/streaming_gateway.py`` (``.stop()`` / ``.disconnect()``),
so it drops directly into ``_BrokerSubscription.unsubscribe()``
(``infrastructure/providers/broker/broker_data_provider.py``) with no changes there.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from domain.ports.broker_stream_gateway import BrokerStreamGateway


class DepthStreamHandle:
    """Handle for a gateway ``stream_depth()`` subscription.

    ``initial`` is the synchronous first snapshot when the broker provides one
    (Dhan does; Upstox does not — ``None`` there). ``stop`` is idempotent.
    """

    def __init__(
        self,
        *,
        initial: Any | None = None,
        on_stop: Callable[[], None] | None = None,
        stream_gateway: BrokerStreamGateway | None = None,
    ) -> None:
        self.initial = initial
        self._on_stop = on_stop
        self._stream_gateway = stream_gateway
        self._stopped = False

    def stop(self, timeout: float | None = None) -> None:
        if self._stopped:
            return
        self._stopped = True
        if self._stream_gateway is not None:
            self._stream_gateway.disconnect()
        if self._on_stop is not None:
            self._on_stop()

    def disconnect(self) -> None:
        self.stop()

    @property
    def is_active(self) -> bool:
        return not self._stopped
