"""Broker gateway factory — composition-root helper (no CLI dependency).

Moved from ``cli.services.broker_registry`` so ``tradex.connect`` can create
live gateways without importing presentation-layer code.

Public API (use these)
----------------------
* :func:`bootstrap_gateway` — create + optional auth probe (composition roots)
* :func:`require_gateway` — bootstrap with probe; raise if not live-ready
* :func:`resolve_env_path`, :func:`list_available_brokers`, ``ENV_FILES``

Private API (internal only)
---------------------------
* :func:`_create_transport_gateway` — transport wiring, no network auth probe
* ``BrokerFactory.create`` / ``UpstoxBrokerFactory.create`` — only via
  ``_create_dhan`` / ``_create_upstox`` in this module

Connect modes
-------------
* **Live** — ``require_gateway`` or ``bootstrap_gateway(require_authenticated=True)``:
  structural check → read-only probe → at most one remint on 401.
* **Analytics** — ``bootstrap_gateway(skip_auth_probe=True)``: transport only,
  explicit TOTP-safe opt-out (still never call ``_create_transport_gateway`` directly).

``create_gateway`` is deprecated; it delegates to ``_create_transport_gateway``.
"""

from __future__ import annotations

import importlib
import logging
import warnings
from pathlib import Path
from typing import Any

from domain.ports.bootstrap import BootstrapResult, BootstrapStatus, classify_exception

logger = logging.getLogger(__name__)

# Convention: env files relative to process CWD / project root
ENV_FILES: dict[str, str | None] = {
    "dhan": ".env.local",
    "upstox": ".env.upstox",
    "paper": None,
    "datalake": None,
}


def resolve_env_path(broker: str, env_path: str | Path | None = None) -> Path | None:
    """Resolve the environment file path for *broker*."""
    if env_path is not None:
        return Path(env_path)
    default = ENV_FILES.get(broker)
    if default is not None:
        return Path(default)
    return None


def list_available_brokers() -> list[dict[str, Any]]:
    """Return registered brokers with env-file availability."""
    result: list[dict[str, Any]] = []
    for name, env_file in ENV_FILES.items():
        available = True
        if env_file is not None:
            available = Path(env_file).exists()
        result.append({"name": name, "env_file": env_file, "available": available})
    return result


def _create_transport_gateway(
    broker: str = "paper",
    env_path: str | Path | None = None,
    load_instruments: bool = True,
    event_bus: Any | None = None,
    lifecycle: Any | None = None,
    risk_manager: Any | None = None,
) -> Any | None:
    """Create transport for *broker* (private — no network auth probe)."""
    broker = (broker or "paper").lower().strip()
    builders = {
        "dhan": _create_dhan,
        "upstox": _create_upstox,
        "paper": _create_paper,
        "datalake": _create_datalake,
    }
    builder = builders.get(broker)
    if builder is None:
        logger.error(
            "Unknown broker %r. Expected one of: %s", broker, sorted(builders)
        )
        return None
    return builder(
        env_path,
        load_instruments=load_instruments,
        event_bus=event_bus,
        lifecycle=lifecycle,
        risk_manager=risk_manager,
    )


def create_gateway(
    broker: str = "paper",
    env_path: str | Path | None = None,
    load_instruments: bool = True,
    event_bus: Any | None = None,
    lifecycle: Any | None = None,
    risk_manager: Any | None = None,
) -> Any | None:
    """Deprecated: use :func:`bootstrap_gateway` or :func:`require_gateway`."""
    warnings.warn(
        "create_gateway is deprecated; use bootstrap_gateway or require_gateway",
        DeprecationWarning,
        stacklevel=2,
    )
    return _create_transport_gateway(
        broker,
        env_path=env_path,
        load_instruments=load_instruments,
        event_bus=event_bus,
        lifecycle=lifecycle,
        risk_manager=risk_manager,
    )


def bootstrap_gateway(
    broker: str = "paper",
    env_path: str | Path | None = None,
    *,
    load_instruments: bool = True,
    event_bus: Any | None = None,
    lifecycle: Any | None = None,
    risk_manager: Any | None = None,
    skip_auth_probe: bool = False,
    require_authenticated: bool | None = None,
    analytics_only: bool = False,
    skip_credential_check: bool = False,
) -> BootstrapResult:
    """Create gateway and automatically run authenticated readiness.

    Flow (live brokers)::

        _create_transport_gateway
          → structural_readiness (token present)
          → execute_read_only_probe (funds/profile)
          → on token rejection: one force-refresh (TOTP under cooldown)
          → re-probe
          → BootstrapResult(READY | REAUTH_REQUIRED | FAILED)

    Paper/datalake skip the network probe and return READY.

    Parameters
    ----------
    skip_auth_probe:
        Skip the network probe (transport only). Prefer this over the legacy
        ``analytics_only`` / ``skip_credential_check`` flags.
    require_authenticated:
        When ``False``, skip the network probe. When ``True`` or ``None``
        (default), run it for live brokers. Integration tests pass
        ``require_authenticated=True`` explicitly.
    analytics_only / skip_credential_check:
        Legacy CLI facade flags; both imply skip probe (transport for reads).
    """
    broker = (broker or "paper").lower().strip()
    resolved = resolve_env_path(broker, env_path)

    # Resolve skip: explicit skip wins; require_authenticated=False skips;
    # legacy analytics flags skip; otherwise probe live brokers.
    skip_probe = bool(skip_auth_probe or analytics_only or skip_credential_check)
    if require_authenticated is False:
        skip_probe = True
    elif require_authenticated is True:
        # Force probe even if a legacy flag was also set (tests / live scripts).
        if not skip_auth_probe:
            skip_probe = False

    try:
        gw = _create_transport_gateway(
            broker,
            env_path=resolved,
            load_instruments=load_instruments,
            event_bus=event_bus,
            lifecycle=lifecycle,
            risk_manager=risk_manager,
        )
    except ValueError as exc:
        return BootstrapResult(
            status=BootstrapStatus.FAILED,
            broker=broker,
            error=str(exc),
        )
    except Exception as exc:
        logger.error("bootstrap_gateway create failed: %s", exc)
        return BootstrapResult(
            status=classify_exception(exc),
            broker=broker,
            error=str(exc),
        )

    if gw is None:
        if broker not in ENV_FILES:
            return BootstrapResult(
                status=BootstrapStatus.FAILED,
                broker=broker,
                error=(
                    f"Unknown broker {broker!r}. "
                    f"Expected one of: {sorted(ENV_FILES)}"
                ),
            )
        return BootstrapResult(
            status=BootstrapStatus.FAILED,
            broker=broker,
            error="_create_transport_gateway returned None",
        )

    # Non-live or explicit skip: no auth probe
    if broker in {"paper", "datalake"} or skip_probe:
        return BootstrapResult(
            status=BootstrapStatus.READY,
            broker=broker,
            gateway=gw,
            probe_passed=True,
            authenticated=True,
            probe_name=f"{broker}_skip",
        )

    from infrastructure.connection.bootstrap_result import structural_readiness_probe
    from infrastructure.connection.authenticated_readiness import (
        authenticated_readiness_probe,
    )

    struct_ok, struct_err = structural_readiness_probe(gw, broker)
    if not struct_ok:
        return BootstrapResult(
            status=BootstrapStatus.REAUTH_REQUIRED,
            broker=broker,
            gateway=None,
            error=struct_err or "structural readiness failed",
            probe_passed=False,
            authenticated=False,
        )

    # Automatic network probe + at most one remint on rejection
    probe = authenticated_readiness_probe(gw, broker, env_path=resolved)
    if probe.ok:
        logger.info(
            "bootstrap_auth_ready",
            extra={
                "broker": broker,
                "probe": probe.probe_name,
                "refreshed": probe.refreshed_token,
            },
        )
        return BootstrapResult(
            status=BootstrapStatus.READY,
            broker=broker,
            gateway=gw,
            probe_passed=True,
            authenticated=True,
            probe_name=probe.probe_name,
            refreshed_token=probe.refreshed_token,
        )

    # Auth failed — do not hand out a dead gateway for live trading
    status = (
        BootstrapStatus.REAUTH_REQUIRED
        if probe.token_rejected
        else BootstrapStatus.FAILED
    )
    logger.warning(
        "bootstrap_auth_failed",
        extra={
            "broker": broker,
            "probe": probe.probe_name,
            "error": probe.error,
            "refreshed": probe.refreshed_token,
            "status": status.value,
        },
    )
    try:
        close = getattr(gw, "close", None)
        if callable(close):
            close()
    except Exception:
        pass

    return BootstrapResult(
        status=status,
        broker=broker,
        gateway=None,
        error=probe.error or "authenticated readiness probe failed",
        probe_passed=True,
        authenticated=False,
        probe_name=probe.probe_name,
        refreshed_token=probe.refreshed_token,
    )


def require_gateway(
    broker: str = "paper",
    env_path: str | Path | None = None,
    *,
    load_instruments: bool = True,
    event_bus: Any | None = None,
    lifecycle: Any | None = None,
    risk_manager: Any | None = None,
) -> Any:
    """Bootstrap gateway with auth probe; raise if not live-ready.

    Production helper for call sites that need a ready gateway or a hard error.
    """
    from domain.errors import BrokerNotReadyError

    result = bootstrap_gateway(
        broker,
        env_path=env_path,
        load_instruments=load_instruments,
        event_bus=event_bus,
        lifecycle=lifecycle,
        risk_manager=risk_manager,
        require_authenticated=True,
    )
    if not result.live_ready:
        raise BrokerNotReadyError.from_bootstrap(result)
    return result.gateway


def _create_dhan(
    env_path: str | Path | None,
    *,
    load_instruments: bool = True,
    event_bus: Any | None = None,
    lifecycle: Any | None = None,
    risk_manager: Any | None = None,
) -> Any | None:
    try:
        _mod = importlib.import_module("brokers.dhan.identity.factory")

        resolved = Path(env_path) if env_path is not None else resolve_env_path("dhan")
        return _mod.BrokerFactory().create(
            env_path=resolved,
            load_instruments=load_instruments,
            event_bus=event_bus,
            lifecycle=lifecycle,
            risk_manager=risk_manager,
        )
    except ImportError:
        logger.warning("Dhan broker package not available")
        return None
    except Exception as exc:
        logger.error("Failed to create Dhan gateway: %s", exc)
        return None


def _create_upstox(
    env_path: str | Path | None,
    *,
    load_instruments: bool = True,
    event_bus: Any | None = None,
    lifecycle: Any | None = None,
    risk_manager: Any | None = None,
) -> Any | None:
    try:
        _mod = importlib.import_module("brokers.upstox.factory")

        resolved = Path(env_path) if env_path is not None else resolve_env_path("upstox")
        return _mod.UpstoxBrokerFactory().create(
            env_path=resolved,
            load_instruments=load_instruments,
            event_bus=event_bus,
            lifecycle=lifecycle,
            risk_manager=risk_manager,
        )
    except ImportError:
        logger.warning("Upstox broker package not available")
        return None
    except Exception as exc:
        logger.error("Failed to create Upstox gateway: %s", exc)
        return None


def _create_paper(
    env_path: Path | None = None,  # noqa: ARG001
    **kwargs: Any,  # noqa: ARG001
) -> Any | None:
    try:
        _mod = importlib.import_module("brokers.paper")

        return _mod.PaperGateway()
    except ImportError:
        logger.warning("Paper gateway not available")
        return None


def _create_datalake(
    env_path: Path | None = None,  # noqa: ARG001
    *,
    root: str = "market_data",
    **kwargs: Any,  # noqa: ARG001
) -> Any | None:
    try:
        from datalake.gateway import DataLakeGateway

        return DataLakeGateway(root=root)
    except ImportError:
        logger.warning("DataLake gateway not available")
        return None
    except Exception as exc:
        logger.error("Failed to create DataLake gateway: %s", exc)
        return None
