"""Active broker session + account refresh — shared by API and UI.

Moved out of ``interface.ui`` so ``interface.api`` does not import UI (F9).
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from domain.universe import Session as DomainSession

logger = logging.getLogger(__name__)

_ENV_PATH = Path(__file__).resolve().parents[3] / ".env.local"


def get_active_session(
    broker_service: Any,
    *,
    mode: str = "market",
    env_path: str | Path | None = None,
) -> DomainSession:
    """Return a broker-bound ``Session`` (DataProvider wired, instruments loaded).

    Prefers ``broker_service.active_broker`` (already auth-probed) and wraps it
    with ``tradex.open_session(gateway=...)``. Falls back to a fresh bootstrap
    when no live gateway is available.
    """
    # Composition seam: application use-case delegates session open to public SDK.
    from tradex.session import open_session

    broker_service._ensure_initialized()
    gw = broker_service.active_broker
    name = broker_service.active_broker_name

    kwargs: dict[str, Any] = {
        "broker": name,
        "mode": mode,
        "load_instruments": True,
    }
    if mode == "trade":
        kwargs["broker_service"] = broker_service

    if gw is not None:
        kwargs["gateway"] = gw
        try:
            return open_session(**kwargs)
        except Exception as exc:  # pragma: no cover - defensive
            logger.warning("active_session: reuse failed, bootstrapping fresh: %s", exc)

    return open_session(
        env_path=env_path or _ENV_PATH,
        **kwargs,
    )


def refresh_account(session: Any) -> Any:
    """Refresh and return session account view (positions, holdings, funds)."""
    if hasattr(session, "stock"):
        acct = session.session.account  # BrokerSession wrapper
    else:
        acct = session.account
    acct.refresh()
    return acct


__all__ = ["get_active_session", "refresh_account"]
