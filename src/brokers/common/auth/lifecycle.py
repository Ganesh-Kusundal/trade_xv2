"""Shared auth lifecycle protocol and 401-once policy helpers."""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class TokenLifecyclePort(Protocol):
    """Broker token lifecycle — implement in dhan/upstox auth modules."""

    broker_id: str

    def describe(self) -> dict[str, Any]: ...

    def bootstrap(self) -> str: ...

    def refresh_on_401(self) -> str | None: ...


def should_attempt_refresh(already_refreshed: bool) -> bool:
    """401-once policy: at most one remint per probe cycle."""
    return not already_refreshed


def merge_auth_error_detail(status_code: int, body: str = "") -> str:
    """Normalize auth failure detail for probes and HTTP clients."""
    if status_code == 401:
        return "token rejected (401)"
    if status_code == 403:
        return "forbidden (403)"
    return body or f"HTTP {status_code}"


def publish_token_lifecycle_event(
    event_bus: Any | None,
    event_name: str,
    *,
    broker_id: str,
    **payload: Any,
) -> None:
    """Publish TOKEN_EXPIRED / TOKEN_REFRESHED when an event bus is available."""
    if event_bus is None:
        try:
            from domain.ports.session_context import get_ambient_session

            session = get_ambient_session()
            event_bus = getattr(session, "event_bus", None) if session is not None else None
        except Exception:
            event_bus = None
    if event_bus is None:
        return
    from domain.events.types import DomainEvent, EventType

    try:
        event_type = EventType[event_name]
    except KeyError:
        return
    publish = getattr(event_bus, "publish", None)
    if not callable(publish):
        return
    publish(
        DomainEvent.now(
            event_type=event_type.value,
            payload={"broker_id": broker_id, **payload},
            source=broker_id,
        )
    )


__all__ = [
    "TokenLifecyclePort",
    "merge_auth_error_detail",
    "publish_token_lifecycle_event",
    "should_attempt_refresh",
]
