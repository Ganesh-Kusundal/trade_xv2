"""Per-session kernel wiring — registry scoped to session, shared quota scheduler."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)

# ponytail: shared process quota scheduler; upgrade path = per-account quotas
_shared_quota: Any | None = None


@dataclass
class SessionKernel:
    """Sync kernel handle attached to a product Session."""

    registry: Any
    quota: Any
    router: Any | None
    broker_id: str
    gateways: list[Any] = field(default_factory=list)


def wire_gateway_for_session(
    gateway: Any,
    broker_id: str,
    *,
    existing_kernel: SessionKernel | None = None,
) -> SessionKernel:
    """Register gateway with session-scoped registry and shared quota profiles."""
    global _shared_quota

    from application.composer.registry import BrokerRegistry
    from application.composer.router import BrokerRouter
    from application.scheduling.quota_scheduler import QuotaScheduler
    from domain.policies.defaults import default_source_selection_policy

    if _shared_quota is None:
        _shared_quota = QuotaScheduler(reserved_headroom=0.20)

    registry = (
        existing_kernel.registry
        if existing_kernel is not None
        else BrokerRegistry()
    )
    gateways = list(existing_kernel.gateways) if existing_kernel is not None else []

    try:
        registry.register(gateway)
        gateways.append(gateway)
    except Exception as exc:
        logger.debug("session_infra: gateway register skipped: %s", exc)

    try:
        caps = gateway.list_capabilities().capabilities
        for profile in caps.rate_limit_profiles:
            _shared_quota.register_profile(broker_id, profile)
    except Exception as exc:
        logger.warning(
            "session_infra: could not register quota profiles for %s: %s", broker_id, exc
        )

    router = None
    try:
        router = BrokerRouter(
            registry=registry,
            policy=default_source_selection_policy(),
            quota_headroom_fn=_shared_quota.headroom_for,
        )
    except Exception as exc:
        logger.debug("session_infra: router wire skipped: %s", exc)

    return SessionKernel(
        registry=registry,
        quota=_shared_quota,
        router=router,
        broker_id=broker_id,
        gateways=gateways,
    )


def get_session_quota_scheduler() -> Any | None:
    return _shared_quota


def get_session_registry() -> Any | None:
    """Deprecated: prefer ``session.kernel.registry`` on the active Session."""
    return None
