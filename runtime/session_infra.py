"""Per-process broker kernel wiring for ``tradex.connect`` (sync quota/registry).

Composition root (``runtime/``): allowed to wire application orchestrators.
Safe-to-trade P0-I: ``open_session`` must not skip quota/router registration.
Full async :func:`runtime.broker_infrastructure.build_infrastructure` remains
available for multi-broker composition roots; this module is the **sync**
path used by ``tradex.connect`` so live order loops still register rate
profiles with :class:`QuotaScheduler`.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger(__name__)

_session_registry: Any | None = None
_session_quota: Any | None = None
_session_router: Any | None = None


@dataclass
class SessionKernel:
    """Lightweight sync kernel handle attached to a product Session."""

    registry: Any
    quota: Any
    router: Any | None
    broker_id: str


def wire_gateway_for_session(gateway: Any, broker_id: str) -> SessionKernel:
    """Register gateway + rate profiles with the process QuotaScheduler.

    Returns a :class:`SessionKernel` so callers can stash the handle on the
    Session (``session.kernel`` / dynamic attr) for diagnostics.
    """
    global _session_registry, _session_quota, _session_router

    from application.composer.registry import BrokerRegistry
    from application.composer.router import BrokerRouter
    from application.scheduling.quota_scheduler import QuotaScheduler
    from domain.policies.defaults import default_source_selection_policy

    if _session_quota is None:
        _session_quota = QuotaScheduler(reserved_headroom=0.20)
    if _session_registry is None:
        _session_registry = BrokerRegistry()

    try:
        _session_registry.register(gateway)
    except Exception as exc:
        logger.debug("session_infra: gateway already registered or register failed: %s", exc)

    try:
        caps = gateway.list_capabilities().capabilities
        for profile in caps.rate_limit_profiles:
            _session_quota.register_profile(broker_id, profile)
    except Exception as exc:
        logger.warning(
            "session_infra: could not register quota profiles for %s: %s", broker_id, exc
        )

    try:
        if _session_router is None:
            _session_router = BrokerRouter(
                registry=_session_registry,
                policy=default_source_selection_policy(),
                quota_headroom_fn=_session_quota.headroom_for,
            )
    except Exception as exc:
        logger.debug("session_infra: router wire skipped: %s", exc)

    return SessionKernel(
        registry=_session_registry,
        quota=_session_quota,
        router=_session_router,
        broker_id=broker_id,
    )


def get_session_quota_scheduler() -> Any | None:
    return _session_quota


def get_session_registry() -> Any | None:
    return _session_registry
