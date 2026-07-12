"""Single seam that builds a broker-bound ``tradex.Session`` for CLI commands.

Reuses the already-auth-probed gateway owned by :class:`BrokerService`
when one exists, so OOP commands never each re-bootstrap auth. Falls
back to a fresh ``tradex.open_session`` bootstrap otherwise (paper / mock /
token-refresh).  This is the *only* place OOP commands touch broker
bootstrap.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from domain.universe import Session as DomainSession

logger = logging.getLogger(__name__)

_ENV_PATH = Path(__file__).resolve().parent.parent.parent / ".env.local"


def get_active_session(
    broker_service: Any,
    *,
    mode: str = "market",
    env_path: str | Path | None = None,
) -> DomainSession:
    """Return a broker-bound ``Session`` (``DataProvider`` wired, instruments loaded).

    Prefers ``broker_service.active_broker`` (already auth-probed by
    ``BrokerService``) and wraps it with ``tradex.open_session(gateway=...)``
    so the ``Session`` + ``DataProvider`` come pre-bound without a second
    network probe.  Falls back to a fresh bootstrap when no live gateway
    is available.
    """
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
