"""Broker infrastructure error hierarchy.

All errors raised by the broker layer are typed so callers can handle specific
failure modes without string matching.  No error in this module leaks broker
wire DTOs or raw response payloads — those stay behind the adapter boundary.
"""

from __future__ import annotations

from typing import Sequence


class BrokerError(Exception):
    """Base class for all broker infrastructure errors."""

    def __init__(self, message: str, broker_id: str | None = None) -> None:
        super().__init__(message)
        self.broker_id = broker_id
        self.message = message


class BrokerUnavailableError(BrokerError):
    """Raised when a broker is unreachable or in an unhealthy state.

    Callers should consult ``BrokerRouter`` for fallback selection rather than
    retrying the same broker immediately.
    """

    def __init__(self, broker_id: str, reason: str = "") -> None:
        super().__init__(
            f"Broker '{broker_id}' is unavailable: {reason}" if reason
            else f"Broker '{broker_id}' is unavailable",
            broker_id=broker_id,
        )
        self.reason = reason


class UnsupportedExtensionError(BrokerError):
    """Raised when an extension interface is requested for a broker that does not support it.

    ``alternatives`` lists broker_ids that do support the requested extension,
    so the caller can route elsewhere instead of failing silently.
    """

    def __init__(
        self,
        broker_id: str,
        extension_name: str,
        alternatives: Sequence[str] = (),
    ) -> None:
        alt_msg = f" Alternatives: {list(alternatives)}" if alternatives else ""
        super().__init__(
            f"Broker '{broker_id}' does not support extension '{extension_name}'.{alt_msg}",
            broker_id=broker_id,
        )
        self.extension_name = extension_name
        self.alternatives = list(alternatives)


class QuotaExhaustedError(BrokerError):
    """Raised when the QuotaScheduler cannot grant a token for a request.

    Carries ``retry_after_seconds`` so callers can back off for the right
    duration instead of polling.
    """

    def __init__(
        self,
        broker_id: str,
        endpoint_class: str,
        priority_class: str,
        retry_after_seconds: float | None = None,
    ) -> None:
        msg = (
            f"Quota exhausted for broker='{broker_id}' "
            f"endpoint='{endpoint_class}' priority='{priority_class}'"
        )
        if retry_after_seconds is not None:
            msg += f"; retry after {retry_after_seconds:.1f}s"
        super().__init__(msg, broker_id=broker_id)
        self.endpoint_class = endpoint_class
        self.priority_class = priority_class
        self.retry_after_seconds = retry_after_seconds


class RoutingError(BrokerError):
    """Raised when no broker can be selected for the requested operation.

    This signals that the policy could not find any healthy, capable broker.
    """

    def __init__(self, operation: str, reason: str = "") -> None:
        super().__init__(
            f"No broker could be selected for operation='{operation}': {reason}"
            if reason else f"No broker could be selected for operation='{operation}'"
        )
        self.operation = operation
        self.reason = reason


class HistoricalFetchError(BrokerError):
    """Raised when a historical data chunk fetch fails at the broker level."""

    def __init__(
        self,
        broker_id: str,
        chunk_id: str,
        reason: str = "",
    ) -> None:
        super().__init__(
            f"Historical fetch failed for chunk='{chunk_id}' on broker='{broker_id}': {reason}",
            broker_id=broker_id,
        )
        self.chunk_id = chunk_id
        self.reason = reason


class StreamError(BrokerError):
    """Base error for stream session failures."""

    def __init__(self, broker_id: str, session_id: str, reason: str = "") -> None:
        super().__init__(
            f"Stream error on broker='{broker_id}' session='{session_id}': {reason}",
            broker_id=broker_id,
        )
        self.session_id = session_id
        self.reason = reason


class StreamAuthError(StreamError):
    """Authentication failure during stream connect or re-auth."""


class StreamStalenessError(StreamError):
    """Raised when a stream session has exceeded its freshness SLA."""

    def __init__(
        self,
        broker_id: str,
        session_id: str,
        stale_seconds: float,
    ) -> None:
        super().__init__(
            broker_id,
            session_id,
            reason=f"no valid data for {stale_seconds:.1f}s",
        )
        self.stale_seconds = stale_seconds


class MergeConflictError(BrokerError):
    """Raised when historical merge encounters irreconcilable bar conflicts and the
    policy is ``fail_on_conflict``.
    """

    def __init__(self, conflict_count: int, chunk_ids: Sequence[str]) -> None:
        super().__init__(
            f"Historical merge conflict: {conflict_count} conflicting bars "
            f"across chunks {list(chunk_ids)}"
        )
        self.conflict_count = conflict_count
        self.chunk_ids = list(chunk_ids)
