"""BrokerRouter — routes operations across multiple broker handles with fallback.

Inspired by Trade_J's BrokerRouter with:
- Manual mode: explicit handle selection
- Auto mode: tries handles in priority order, falling back on failure

Usage::
    router = BrokerRouter(handles=[dhan, upstox, icici], default=dhan)

    # Auto-route with fallback
    result = router.route(lambda h: h.get_provider(MARKET_DATA).get_quote("2885"))

    # Explicit routing
    result = router.route_to("DHAN", lambda h: ...)
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from brokers.common.core.connection import Capability
from brokers.common.core.result import GatewayResult
from brokers.handle import BrokerHandle


class BrokerRouter:
    """Routes broker operations across registered handles."""

    def __init__(
        self,
        handles: list[BrokerHandle] | None = None,
        default: BrokerHandle | None = None,
    ):
        self._handles: dict[str, BrokerHandle] = {}
        self._default: BrokerHandle | None = None

        if handles:
            for h in handles:
                self._handles[h.broker_id] = h
        if default:
            self._default = default
        elif handles:
            self._default = handles[0]

    # ── Handle Registry ──────────────────────────────────────────

    @property
    def handles(self) -> list[BrokerHandle]:
        return list(self._handles.values())

    @property
    def default_handle(self) -> BrokerHandle | None:
        return self._default

    def register(self, handle: BrokerHandle) -> None:
        """Register a broker handle."""
        self._handles[handle.broker_id] = handle

    def remove(self, broker_id: str) -> None:
        """Remove a registered broker handle by ID."""
        self._handles.pop(broker_id, None)
        if self._default and self._default.broker_id == broker_id:
            self._default = None

    def get(self, broker_id: str) -> BrokerHandle | None:
        """Get a specific handle by ID."""
        return self._handles.get(broker_id)

    # ── Discovery ────────────────────────────────────────────────

    def find_by_capability(self, capability: Capability) -> list[BrokerHandle]:
        """Find all handles that support a given capability."""
        return [h for h in self.handles if h.has_capability(capability)]

    # ── Routing ───────────────────────────────────────────────────

    def route(
        self,
        operation: Callable[[BrokerHandle], GatewayResult[Any]],
        fallback: bool = True,
    ) -> GatewayResult[Any]:
        """Execute ``operation`` on the default handle with optional fallback.

        If ``fallback`` is True and the default handle fails, remaining
        handles are tried in registration order.
        """
        if not self._default:
            return GatewayResult.failure("No default broker configured")

        candidates = [self._default]
        if fallback:
            candidates.extend(h for h in self.handles if h.broker_id != self._default.broker_id)

        last_error = None
        for handle in candidates:
            result = operation(handle)
            if result.is_success:
                return result
            last_error = result.error

        error_msg = str(last_error) if last_error else "All brokers failed"
        return GatewayResult.failure(f"All brokers failed: {error_msg}")

    def route_to(
        self,
        broker_id: str,
        operation: Callable[[BrokerHandle], GatewayResult[Any]],
    ) -> GatewayResult[Any]:
        """Execute ``operation`` on a specific handle by ID."""
        handle = self._handles.get(broker_id)
        if handle is None:
            raise ValueError(f"Broker '{broker_id}' not found")
        return operation(handle)
