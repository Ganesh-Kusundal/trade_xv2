"""Broker gateway factory — composition-root helper (no CLI dependency).

Moved from ``cli.services.broker_registry`` so ``tradex.connect`` can create
live gateways without importing presentation-layer code.

Public API (use these)
----------------------
* :func:`bootstrap_gateway` — create + optional auth probe (composition roots)
* :func:`require_gateway` — bootstrap with probe; raise if not live-ready
* :func:`resolve_env_path`, :func:`list_available_brokers`

Private API (internal only)
---------------------------
* :func:`_create_transport_gateway` — transport wiring, no network auth probe

Connect modes
-------------
* **Live** — ``require_gateway`` or ``bootstrap_gateway(require_authenticated=True)``:
  structural check → read-only probe → at most one remint on 401.
* **Analytics** — ``bootstrap_gateway(skip_auth_probe=True)``: transport only,
  explicit TOTP-safe opt-out (still never call ``_create_transport_gateway`` directly).
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from domain.ports.bootstrap import BootstrapResult, BootstrapStatus, classify_exception

logger = logging.getLogger(__name__)


def _env_file_for_broker(broker: str) -> str | None:
    """Return the env file path for *broker* from the BrokerPlugin registry."""
    from infrastructure.broker_plugin import ensure_core_plugins, get_broker_plugin

    ensure_core_plugins()
    plugin = get_broker_plugin(broker)
    return plugin.env_file if plugin is not None else None


def _is_live_broker(broker: str) -> bool:
    """Return True if *broker* is a live (non-paper) broker."""
    from infrastructure.broker_plugin import ensure_core_plugins, get_broker_plugin

    ensure_core_plugins()
    plugin = get_broker_plugin(broker)
    return plugin.is_live if plugin is not None else True


def resolve_env_path(broker: str, env_path: str | Path | None = None) -> Path | None:
    """Resolve the environment file path for *broker*."""
    from infrastructure.auth.credential_resolver import CredentialResolver

    resolved = CredentialResolver.resolve_env_path(broker, env_path)
    if resolved is not None:
        return resolved
    default = _env_file_for_broker(broker)
    if default is not None:
        return Path(default)
    return None


def list_available_brokers() -> list[dict[str, Any]]:
    """Return registered brokers with env-file availability."""
    from infrastructure.broker_plugin import ensure_core_plugins, list_broker_plugins

    ensure_core_plugins()
    result: list[dict[str, Any]] = []
    for plugin in list_broker_plugins():
        env_file = plugin.env_file
        available = True
        if env_file is not None:
            available = Path(env_file).exists()
        result.append({"name": plugin.broker_id, "env_file": env_file, "available": available})
    return result


def env_files() -> dict[str, str]:
    """Return ``{broker_id: env_file_path}`` for every registered broker.

    Replaces the old module-level ``ENV_FILES`` dict (removed when env-file
    resolution moved to the plugin registry). Rebuilt lazily so it always
    reflects the current plugin set.
    """
    from infrastructure.broker_plugin import ensure_core_plugins, list_broker_plugins

    ensure_core_plugins()
    return {
        plugin.broker_id: plugin.env_file
        for plugin in list_broker_plugins()
        if plugin.env_file is not None
    }


# Back-compat alias: callers/tests still reference ``ENV_FILES``; resolved live.
def __getattr__(name: str) -> Any:
    if name == "ENV_FILES":
        return env_files()
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


# ── Gateway builders — plugin-driven dispatch ──────────────────────────────

# Builder functions keyed by broker_id. Canonical registration path:
# ``runtime.broker_builders`` registers builders lazily via
# ``_ensure_default_builders()`` — not at broker package import time.
_GATEWAY_BUILDERS: dict[str, callable] = {}


def register_gateway_builder(broker_id: str, builder: callable) -> None:
    """Register a gateway builder function for a broker."""
    _GATEWAY_BUILDERS[broker_id] = builder


def _ensure_default_builders() -> None:
    """Register default gateway builders if not already registered.

    Builders live in ``runtime.broker_builders`` (composition root) and are
    imported lazily so ``infrastructure`` never statically depends on broker
    packages at import time.
    """
    if _GATEWAY_BUILDERS:
        return
    from runtime.broker_builders import (
        create_datalake_gateway,
        create_dhan_gateway,
        create_paper_gateway,
        create_upstox_gateway,
    )

    register_gateway_builder("dhan", create_dhan_gateway)
    register_gateway_builder("upstox", create_upstox_gateway)
    register_gateway_builder("paper", create_paper_gateway)
    register_gateway_builder("datalake", create_datalake_gateway)


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
    _ensure_default_builders()
    builder = _GATEWAY_BUILDERS.get(broker)
    if builder is None:
        logger.error("Unknown broker %r. Expected one of: %s", broker, sorted(_GATEWAY_BUILDERS))
        return None
    resolved = resolve_env_path(broker, env_path)
    try:
        return builder(
            resolved,
            load_instruments=load_instruments,
            event_bus=event_bus,
            lifecycle=lifecycle,
            risk_manager=risk_manager,
        )
    except Exception as exc:
        logger.error("gateway_create_failed broker=%s: %s", broker, exc)
        return None


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
        from infrastructure.broker_plugin import ensure_core_plugins, list_broker_plugins

        ensure_core_plugins()
        known_brokers = [p.broker_id for p in list_broker_plugins()]
        if broker not in known_brokers:
            return BootstrapResult(
                status=BootstrapStatus.FAILED,
                broker=broker,
                error=(f"Unknown broker {broker!r}. Expected one of: {sorted(known_brokers)}"),
            )
        return BootstrapResult(
            status=BootstrapStatus.FAILED,
            broker=broker,
            error="_create_transport_gateway returned None",
        )

    # Non-live or explicit skip: no auth probe
    if not _is_live_broker(broker) or skip_probe:
        return BootstrapResult(
            status=BootstrapStatus.READY,
            broker=broker,
            gateway=gw,
            probe_passed=True,
            authenticated=True,
            probe_name=f"{broker}_skip",
        )

    from infrastructure.connection.authenticated_readiness import (
        authenticated_readiness_probe,
    )
    from infrastructure.connection.bootstrap_result import structural_readiness_probe

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
    status = BootstrapStatus.REAUTH_REQUIRED if probe.token_rejected else BootstrapStatus.FAILED
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
    from domain.exceptions import BrokerNotReadyError

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
