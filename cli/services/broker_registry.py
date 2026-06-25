"""Broker registry — unified broker-agnostic factory for creating gateways.

Phase 4: single point of truth for broker gateway creation.  All env file
paths and factory dispatch logic live here so neither ``BrokerService``
nor ``cli/main.py`` duplicate them.

Usage::

    from cli.services.broker_registry import bootstrap_gateway, create_gateway

    result = bootstrap_gateway("dhan")
    if result.ok:
        gw = result.gateway

    # Backward-compatible helper (returns gateway or None)
    gw = create_gateway("dhan")
"""

from __future__ import annotations

import logging
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from brokers.common.auth.credential_resolver import CANONICAL_ENV_FILES, CredentialResolver
from brokers.common.auth.credential_validator import CredentialValidator
from brokers.common.connection.authenticated_readiness import authenticated_readiness_probe
from brokers.common.connection.bootstrap_result import (
    BootstrapResult,
    BootstrapStatus,
    classify_exception,
    structural_readiness_probe,
)
from brokers.common.connection.errors import BrokerNotReadyError

logger = logging.getLogger(__name__)

# Re-export for backward compatibility
ENV_FILES = CANONICAL_ENV_FILES


def resolve_env_path(broker: str, env_path: str | Path | None = None) -> Path | None:
    """Resolve the environment file path for *broker*."""
    return CredentialResolver.resolve_env_path(broker, env_path)


def bootstrap_gateway(
    broker: str = "dhan",
    env_path: str | Path | None = None,
    load_instruments: bool = True,
    event_bus: Any | None = None,
    lifecycle: Any | None = None,
    risk_manager: Any | None = None,
    *,
    analytics_only: bool = False,
    skip_credential_check: bool = False,
    require_authenticated: bool = True,
    smart: bool = False,  # NEW: Enable intelligent gateway
) -> BootstrapResult:
    """Create a gateway with typed success/failure semantics."""
    broker = broker.lower().strip()

    if not skip_credential_check and broker != "paper":
        ok, issues = CredentialValidator.validate_broker(broker, env_path)
        if not ok:
            messages = "; ".join(i.message for i in issues if i.severity == "error")
            return BootstrapResult(
                status=BootstrapStatus.REAUTH_REQUIRED,
                broker=broker,
                error=messages or "credential validation failed",
            )

    builders = {
        "dhan": _create_dhan,
        "upstox": _create_upstox,
        "paper": _create_paper,
    }
    builder = builders.get(broker)
    if builder is None:
        msg = f"Unknown broker: {broker} (expected one of {list(builders)})"
        logger.error(msg)
        return BootstrapResult(status=BootstrapStatus.FAILED, broker=broker, error=msg)

    try:
        gateway = builder(
            env_path,
            load_instruments=load_instruments,
            event_bus=event_bus,
            lifecycle=lifecycle,
            risk_manager=risk_manager,
            analytics_only=analytics_only,
        )
    except ImportError as exc:
        logger.warning("%s broker not installed: %s", broker, exc)
        return BootstrapResult(
            status=BootstrapStatus.FAILED,
            broker=broker,
            error=str(exc),
        )
    except Exception as exc:
        status = classify_exception(exc)
        logger.error("Failed to create %s gateway: %s", broker, exc)
        return BootstrapResult(status=status, broker=broker, error=str(exc))

    if gateway is None:
        return BootstrapResult(
            status=BootstrapStatus.FAILED,
            broker=broker,
            error="factory returned None",
        )

    probe_ok, probe_err = structural_readiness_probe(gateway, broker)
    if not probe_ok:
        return BootstrapResult(
            status=BootstrapStatus.DEGRADED,
            broker=broker,
            gateway=gateway,
            error=probe_err,
            probe_passed=False,
            authenticated=False,
        )

    if broker == "paper" or not require_authenticated:
        return BootstrapResult(
            status=BootstrapStatus.READY,
            broker=broker,
            gateway=gateway,
            probe_passed=True,
            authenticated=(broker == "paper"),
            probe_name="structural_only" if broker != "paper" else "paper_skip",
        )

    auth_result = authenticated_readiness_probe(gateway, broker, env_path=env_path)
    if auth_result.ok:
        # NEW: Wrap in intelligent gateway if requested
        if smart:
            try:
                import asyncio
                from brokers.common.bootstrap import create_intelligent_gateway
                
                # Create intelligent gateway with single broker
                intelligent_gw = asyncio.run(create_intelligent_gateway(
                    [(broker, gateway)],
                    smart=True,
                    primary_broker=broker
                ))
                logger.info("Created intelligent gateway for %s", broker)
                gateway = intelligent_gw
            except Exception as exc:
                logger.warning("Failed to create intelligent gateway, using direct gateway: %s", exc)
                # Fall back to direct gateway
        
        return BootstrapResult(
            status=BootstrapStatus.READY,
            broker=broker,
            gateway=gateway,
            probe_passed=True,
            authenticated=True,
            probe_name=auth_result.probe_name,
            refreshed_token=auth_result.refreshed_token,
        )

    status = (
        BootstrapStatus.REAUTH_REQUIRED if auth_result.token_rejected else BootstrapStatus.FAILED
    )
    return BootstrapResult(
        status=status,
        broker=broker,
        gateway=gateway,
        error=auth_result.error or "authenticated readiness probe failed",
        probe_passed=True,
        authenticated=False,
        probe_name=auth_result.probe_name,
        refreshed_token=auth_result.refreshed_token,
    )


def create_gateway(
    broker: str = "dhan",
    env_path: str | Path | None = None,
    load_instruments: bool = True,
    event_bus: Any | None = None,
    lifecycle: Any | None = None,
    risk_manager: Any | None = None,
    *,
    analytics_only: bool = False,
    require_authenticated: bool = True,
    raise_on_failure: bool = False,
) -> Any | None:
    """Create a gateway for the specified broker.

    Prefer :func:`bootstrap_gateway` for typed outcomes. When
    *raise_on_failure* is ``True``, raises :class:`BrokerNotReadyError`
    instead of returning ``None``.
    """
    result = bootstrap_gateway(
        broker,
        env_path=env_path,
        load_instruments=load_instruments,
        event_bus=event_bus,
        lifecycle=lifecycle,
        risk_manager=risk_manager,
        analytics_only=analytics_only,
        require_authenticated=require_authenticated,
    )
    if not result.ok:
        if raise_on_failure:
            raise BrokerNotReadyError.from_bootstrap(result)
        if result.error:
            logger.debug("create_gateway(%s) failed: %s", broker, result.error)
        return None
    return result.gateway


def require_gateway(
    broker: str = "dhan",
    env_path: str | Path | None = None,
    load_instruments: bool = True,
    event_bus: Any | None = None,
    lifecycle: Any | None = None,
    risk_manager: Any | None = None,
    *,
    analytics_only: bool = False,
    require_authenticated: bool = True,
) -> Any:
    """Create a gateway or raise :class:`BrokerNotReadyError` with bootstrap details."""
    return create_gateway(
        broker,
        env_path=env_path,
        load_instruments=load_instruments,
        event_bus=event_bus,
        lifecycle=lifecycle,
        risk_manager=risk_manager,
        analytics_only=analytics_only,
        require_authenticated=require_authenticated,
        raise_on_failure=True,
    )


def list_available_brokers() -> list[dict[str, Any]]:
    """Return registered brokers with credential-aware availability."""
    result: list[dict[str, Any]] = []
    for name, env_file in ENV_FILES.items():
        available = True if name == "paper" else CredentialValidator.broker_available(name)
        result.append(
            {
                "name": name,
                "env_file": env_file,
                "available": available,
            }
        )
    return result


# ── Broker-specific builders ────────────────────────────────────────────────


def _create_dhan(
    env_path: str | Path | None,
    *,
    load_instruments: bool = True,
    event_bus: Any | None = None,
    lifecycle: Any | None = None,
    risk_manager: Any | None = None,
    analytics_only: bool = False,
) -> Any:
    from brokers.dhan.factory import BrokerFactory

    resolved = Path(env_path) if env_path is not None else None
    return BrokerFactory().create(
        env_path=resolved,
        load_instruments=load_instruments,
        event_bus=event_bus,
        lifecycle=lifecycle,
        risk_manager=risk_manager,
    )


def _create_upstox(
    env_path: str | Path | None,
    *,
    load_instruments: bool = True,
    event_bus: Any | None = None,
    lifecycle: Any | None = None,
    risk_manager: Any | None = None,
    analytics_only: bool = False,
) -> Any:
    from brokers.upstox.factory import UpstoxBrokerFactory

    resolved = Path(env_path) if env_path is not None else None
    return UpstoxBrokerFactory().create(
        env_path=resolved,
        load_instruments=load_instruments,
        event_bus=event_bus,
        lifecycle=lifecycle,
        risk_manager=risk_manager,
        analytics_only=analytics_only,
    )


def _create_paper(
    env_path: Path | None = None,
    **kwargs: Any,
) -> Any:
    from brokers.paper import PaperGateway

    return PaperGateway()


async def bootstrap_infrastructure(
    broker_names: Sequence[str] | None = None,
    *,
    policy: Any | None = None,
    **bootstrap_kwargs: Any,
) -> Any:
    """Bootstrap full BrokerInfrastructure from named brokers."""
    from brokers.common.bootstrap import bootstrap_from_broker_registry, policy_from_env

    names = list(broker_names) if broker_names is not None else ["dhan", "upstox", "paper"]
    return await bootstrap_from_broker_registry(
        names,
        policy=policy or policy_from_env(),
        **bootstrap_kwargs,
    )
