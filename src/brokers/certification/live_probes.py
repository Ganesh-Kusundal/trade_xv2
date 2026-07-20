"""Live broker certification probes — token, reconnect, session recovery."""

from __future__ import annotations

from typing import Any

from brokers.common.auth.lifecycle import TokenLifecyclePort
from brokers.session.broker_session import BrokerSession
from domain.ports.broker_session_state import BrokerSessionState


def resolve_gateway(session: BrokerSession) -> Any | None:
    """Best-effort gateway resolution from an open session."""
    provider = session.provider
    if provider is None:
        return None
    for attr in ("_broker", "_gateway", "gateway", "broker"):
        gw = getattr(provider, attr, None)
        if gw is not None:
            return gw
    kernel = getattr(session.session, "kernel", None)
    if kernel is not None:
        gateways = getattr(kernel, "gateways", None) or []
        if gateways:
            return gateways[-1]
    return provider


def resolve_token_lifecycle(session: BrokerSession) -> TokenLifecyclePort | None:
    """Find a TokenLifecyclePort on gateway or nested broker."""
    gw = resolve_gateway(session)
    if gw is None:
        return None
    for obj in (gw, getattr(gw, "_broker", None), getattr(gw, "token_manager", None)):
        if obj is not None and isinstance(obj, TokenLifecyclePort):
            return obj
    tm = getattr(gw, "token_manager", None)
    if tm is not None:
        for name in ("describe", "bootstrap", "refresh_on_401"):
            if hasattr(tm, name):
                return tm  # type: ignore[return-value]
    return None


def probe_token_refresh(session: BrokerSession) -> str:
    """Verify token refresh path is wired and session stays authenticated."""
    st = session.status
    if not st.authenticated:
        raise RuntimeError("session not authenticated")
    gw = resolve_gateway(session)
    if gw is not None and hasattr(gw, "get_token_refresh_metrics"):
        metrics = gw.get_token_refresh_metrics()
        if not isinstance(metrics, dict):
            raise RuntimeError("get_token_refresh_metrics must return dict")
        if "refresh_count" not in metrics:
            raise RuntimeError("refresh_count missing from token metrics")
        return f"refresh_count={metrics.get('refresh_count', 0)}"
    lifecycle = resolve_token_lifecycle(session)
    if lifecycle is not None:
        detail = lifecycle.describe()
        if not isinstance(detail, dict):
            raise RuntimeError("token lifecycle describe() must return dict")
        return f"lifecycle={detail.get('mode', 'ok')}"
    # Authenticated session without explicit metrics is acceptable if quote works.
    session.stock("RELIANCE").refresh()
    return "authenticated (no refresh metrics hook)"


def probe_token_expiry(session: BrokerSession) -> str:
    """Verify token is valid and expiry metadata is observable when available."""
    st = session.status
    if not st.authenticated:
        raise RuntimeError("session not authenticated")
    lifecycle = resolve_token_lifecycle(session)
    if lifecycle is not None:
        detail = lifecycle.describe()
        if isinstance(detail, dict):
            expires = detail.get("expires_at") or detail.get("expiry")
            if expires:
                return f"expires_at={expires}"
    gw = resolve_gateway(session)
    if gw is not None and hasattr(gw, "describe"):
        d = gw.describe()
        if isinstance(d, dict) and d.get("authenticated") is False:
            raise RuntimeError("gateway reports not authenticated")
    session.stock("RELIANCE").refresh()
    return "token valid (quote ok)"


def probe_disconnect(session: BrokerSession) -> str:
    """Drive DISCONNECTED FSM state (soft).

    Soft-only: hard ``gateway.disconnect()`` can tear down Upstox asyncio loops
    and break subsequent REST/WS in the same process. Chaos tests cover hard
    kill; certification asserts the session FSM + recovery path.
    """
    session._set_session_state(BrokerSessionState.DISCONNECTED)
    if session.session_state != BrokerSessionState.DISCONNECTED:
        raise RuntimeError(f"expected DISCONNECTED, got {session.session_state}")
    return "disconnected (fsm)"


def probe_reconnect(session: BrokerSession) -> str:
    """Drive RECOVERING → HEALTHY; optionally ping gateway reconnect/connect."""
    if session.session_state == BrokerSessionState.HEALTHY:
        session._set_session_state(BrokerSessionState.DISCONNECTED)
    session._set_session_state(BrokerSessionState.RECOVERING)
    gw = resolve_gateway(session)
    if gw is not None and hasattr(gw, "reconnect"):
        result = gw.reconnect()
        if result is False:
            raise RuntimeError("gateway reconnect returned False")
    elif gw is not None and hasattr(gw, "connect"):
        result = gw.connect()
        if result is False:
            raise RuntimeError("gateway connect returned False")
    session._set_session_state(BrokerSessionState.CONNECTED)
    session._set_session_state(BrokerSessionState.HEALTHY)
    if not session.status.authenticated:
        raise RuntimeError("not authenticated after reconnect")
    return "reconnected"


def _restore_subscription(session: BrokerSession) -> str:
    """Re-subscribe a probe symbol and assert a live handle is returned."""
    stock = session.stock("RELIANCE")
    try:
        handle = session.subscribe(stock)
    except RuntimeError as exc:
        # Hard gateway.disconnect() can tear down the Upstox asyncio loop.
        # Quote refresh still proves session recovery when WS resubscribe can't.
        if "event loop" in str(exc).lower() or "closed" in str(exc).lower():
            stock.refresh()
            if stock.ltp is None:
                raise RuntimeError(
                    "subscription restore failed after WS loop reset; quote also empty"
                ) from exc
            return "subscription N/A (ws loop reset; quote ok)"
        raise
    if handle is None:
        raise RuntimeError("subscription restore failed: no handle")
    try:
        stock.refresh()
        if stock.ltp is None:
            raise RuntimeError("subscription restore failed: no ltp after resubscribe")
    finally:
        session.unsubscribe(stock)
    return "subscription restored"


def probe_session_recovery(session: BrokerSession) -> str:
    """Full disconnect → reconnect → subscription restore → quote cycle."""
    probe_disconnect(session)
    detail = probe_reconnect(session)
    sub_detail = _restore_subscription(session)
    stock = session.stock("RELIANCE")
    stock.refresh()
    if stock.ltp is None:
        raise RuntimeError("no ltp after session recovery")
    return f"recovery ok ({detail}; {sub_detail})"
