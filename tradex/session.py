"""tradex.Session — public composition-root factory.

Usage::

    import tradex

    session = tradex.connect("paper")                      # mode=sim (default)
    session = tradex.connect("dhan", mode="market")        # auth + data; no live OMS
    session = tradex.connect("dhan", mode="trade")         # requires process OMS
    session = tradex.connect("upstox", env_path=".env.upstox")
    reliance = session.universe.equity("RELIANCE")
    result = session.buy(reliance, 10, price=2500)        # sim/trade only
    # OrderIntent → Risk → OMS → ExecutionProvider
"""

from __future__ import annotations

import uuid
from pathlib import Path
from typing import Any

from domain.connect_errors import (
    AUTH_FAILED,
    ENG_011,
    GATEWAY_FAILED,
    OMS_REQUIRED,
    UNKNOWN_BROKER,
    UNKNOWN_MODE,
    ConnectError,
)
from domain.session_status import (
    MODE_MARKET,
    MODE_SIM,
    MODE_TRADE,
    PHASE_READY_MARKET,
    PHASE_READY_TRADE,
    VALID_MODES,
    SessionStatus,
)
from domain.universe import Session as DomainSession
from infrastructure.broker_plugin import ensure_core_plugins, get_broker_plugin


def _default_mode(broker_id: str) -> str:
    ensure_core_plugins()
    plugin = get_broker_plugin(broker_id)
    if plugin is not None:
        return plugin.default_mode
    if broker_id == "paper":
        return MODE_SIM
    return MODE_MARKET


def _is_live(broker_id: str) -> bool:
    ensure_core_plugins()
    plugin = get_broker_plugin(broker_id)
    if plugin is not None:
        return plugin.is_live
    return broker_id in {"dhan", "upstox"}


def _normalize_mode(broker_id: str, mode: str | None) -> str:
    ensure_core_plugins()
    plugin = get_broker_plugin(broker_id)
    resolved = (mode or _default_mode(broker_id)).lower().strip()
    if resolved not in VALID_MODES:
        raise ConnectError(
            f"Unknown connect mode {mode!r}.",
            code=UNKNOWN_MODE,
            broker_id=broker_id,
            mode=str(mode or ""),
            remediation=f"Use one of: {', '.join(sorted(VALID_MODES))}.",
        )
    if plugin is not None:
        # Paper: market/trade alias to sim
        if broker_id == "paper" and resolved in {MODE_MARKET, MODE_TRADE}:
            return MODE_SIM
        if resolved not in plugin.supported_modes and broker_id != "paper":
            if resolved == MODE_SIM and plugin.is_live:
                raise ConnectError(
                    f"mode='sim' is only valid for paper.",
                    code=UNKNOWN_MODE,
                    broker_id=broker_id,
                    mode=resolved,
                    remediation="Use mode='market' (data) or mode='trade' (OMS).",
                )
    else:
        if broker_id == "paper" and resolved in {MODE_MARKET, MODE_TRADE}:
            return MODE_SIM
        if _is_live(broker_id) and resolved == MODE_SIM:
            raise ConnectError(
                f"mode='sim' is only valid for paper.",
                code=UNKNOWN_MODE,
                broker_id=broker_id,
                mode=resolved,
                remediation="Use mode='market' (data) or mode='trade' (OMS).",
            )
    return resolved


def open_session(
    broker: str = "paper",
    *,
    mode: str | None = None,
    provider: Any | None = None,
    event_bus: Any | None = None,
    gateway: Any | None = None,
    execution_provider: Any | None = None,
    order_service: Any | None = None,
    use_oms: bool = True,
    env_path: str | Path | None = None,
    load_instruments: bool = True,
    profile: str | None = None,  # reserved for future config profiles
) -> DomainSession:
    """Create a domain ``Session`` bound to a broker or injected provider.

    Parameters
    ----------
    broker:
        ``"paper"``, ``"dhan"``, ``"upstox"``, or ``"datalake"`` (read-only).
    mode:
        ``"sim"`` | ``"market"`` | ``"trade"``.

        - **sim** (paper default): in-memory OMS; LIMIT rests OPEN, MARKET fills.
        - **market** (dhan/upstox default): auth + live data; **orders disabled**.
        - **trade**: live orders via process OMS. Raises :class:`ConnectError`
          ``OMS_REQUIRED`` if no composition-root OMS is registered.
    """
    del profile  # reserved
    ensure_core_plugins()
    broker_id = (broker or "paper").lower().strip()
    plugin = get_broker_plugin(broker_id)
    trace_id = uuid.uuid4().hex[:16]

    try:
        resolved_mode = _normalize_mode(broker_id, mode)
    except ConnectError as exc:
        if not exc.trace_id:
            exc.trace_id = trace_id
        raise

    data = provider
    executor = execution_provider
    oms = order_service
    gw = gateway

    # ── Ensure broker packages self-register adapters ─────────────────
    _ensure_broker_registered(broker_id)

    # ── Build gateway when needed (automatic auth bootstrap) ──────────
    # Production path: create → structural check → network probe → one
    # token remint on rejection. Never hand out a dead live gateway.
    _session_kernel = None
    if gw is None and data is None and executor is None:
        from domain.ports.bootstrap import BootstrapStatus
        from infrastructure.gateway.factory import bootstrap_gateway

        try:
            boot = bootstrap_gateway(
                broker_id,
                env_path=env_path,
                load_instruments=load_instruments,
                event_bus=event_bus,
                require_authenticated=True,
            )
        except Exception as exc:
            raise ConnectError(
                f"Failed to create gateway for broker {broker_id!r}: {exc}",
                code=GATEWAY_FAILED,
                broker_id=broker_id,
                mode=resolved_mode,
                trace_id=trace_id,
                remediation=(
                    f"Check credentials/env file "
                    f"({env_path or (plugin.env_file if plugin else 'default')})."
                ),
            ) from exc

        if not boot.ok or boot.gateway is None:
            err = boot.error or f"status={boot.status.value}"
            unknown = "Unknown broker" in err
            reauth = boot.status == BootstrapStatus.REAUTH_REQUIRED
            code = (
                UNKNOWN_BROKER
                if unknown
                else AUTH_FAILED
                if reauth
                else GATEWAY_FAILED
            )
            remediation = (
                "Use paper, dhan, upstox, or datalake."
                if unknown
                else (
                    "Token rejected or expired. Re-run doctor auth / refresh TOTP "
                    f"credentials ({env_path or (plugin.env_file if plugin else 'default')})."
                    if reauth
                    else (
                        f"Check credentials/env file "
                        f"({env_path or (plugin.env_file if plugin else 'default')})."
                    )
                )
            )
            raise ConnectError(
                f"Failed to bootstrap gateway for broker {broker_id!r}: {err}",
                code=code,
                broker_id=broker_id,
                mode=resolved_mode,
                trace_id=trace_id,
                remediation=remediation,
                details={
                    "bootstrap_status": boot.status.value,
                    "probe_name": boot.probe_name,
                    "refreshed_token": boot.refreshed_token,
                },
            )
        gw = boot.gateway

    # P0-I: register quota profiles + router whenever we have a concrete gateway
    if gw is not None and broker_id not in {"datalake"}:
        from infrastructure.session.infra import wire_gateway_for_session

        try:
            _session_kernel = wire_gateway_for_session(gw, broker_id)
        except Exception as exc:  # defensive — never block connect on kernel wire
            import logging

            logging.getLogger(__name__).warning(
                "session kernel wire failed for %s: %s", broker_id, exc
            )

    # ── Data provider ─────────────────────────────────────────────────
    if data is None:
        if broker_id == "paper":
            from brokers.paper.data_provider import PaperDataProvider

            data = PaperDataProvider(gw)
        elif gw is not None:
            from infrastructure.adapter_factory import create_data_adapter

            data = create_data_adapter(gw, broker_id=broker_id)
        else:
            raise ConnectError(
                "No data provider or gateway available for session",
                code=GATEWAY_FAILED,
                broker_id=broker_id,
                mode=resolved_mode,
                trace_id=trace_id,
            )

    live = _is_live(broker_id)
    orders_wanted = resolved_mode in {MODE_SIM, MODE_TRADE}

    # ── Execution provider ────────────────────────────────────────────
    if executor is None and gw is not None and broker_id != "datalake":
        if broker_id == "paper":
            from brokers.paper.execution_provider import PaperExecutionProvider

            executor = PaperExecutionProvider(gw)
        else:
            from infrastructure.adapter_factory import create_execution_provider

            executor = create_execution_provider(gw, broker_id=broker_id)
            if executor is None:
                from infrastructure.gateway.execution import GatewayExecutionProvider

                executor = GatewayExecutionProvider(gw, broker_id=broker_id)

    # ── OMS spine ─────────────────────────────────────────────────────
    if not use_oms and live and executor is not None and orders_wanted:
        raise ConnectError(
            f"use_oms=False is not allowed for live broker {broker_id!r}.",
            code=ENG_011,
            broker_id=broker_id,
            mode=resolved_mode,
            trace_id=trace_id,
            remediation="Orders must pass OrderIntent → Risk → OMS. (ENG-011)",
        )

    if oms is None and use_oms and executor is not None and orders_wanted:
        from application.oms.session_bridge import build_oms_service

        try:
            oms = build_oms_service(
                executor,
                event_bus=event_bus,
                broker_id=broker_id,
            )
        except RuntimeError as exc:
            msg = str(exc)
            if live and resolved_mode == MODE_TRADE:
                raise ConnectError(
                    "Process OMS composition root required for live trade mode.",
                    code=OMS_REQUIRED,
                    broker_id=broker_id,
                    mode=resolved_mode,
                    trace_id=trace_id,
                    remediation=(
                        "Start CLI/API TradingContext first, or use mode='market' "
                        "for data-only."
                    ),
                    details={"original": msg},
                ) from exc
            raise ConnectError(
                msg,
                code=OMS_REQUIRED if "ENG-001" in msg or "phantom" in msg.lower() else "OMS_FAILED",
                broker_id=broker_id,
                mode=resolved_mode,
                trace_id=trace_id,
            ) from exc

    orders_enabled = oms is not None and orders_wanted
    phase = PHASE_READY_TRADE if orders_enabled else PHASE_READY_MARKET
    status = SessionStatus(
        phase=phase,
        broker_id=broker_id,
        mode=resolved_mode,
        orders_enabled=orders_enabled,
        authenticated=True,
        instruments_loaded=load_instruments or broker_id == "paper",
        trace_id=trace_id,
    )

    session = DomainSession(
        data,
        event_bus=event_bus,
        execution_provider=executor,
        order_service=oms,
        status=status,
    )
    if gw is not None:
        session.attach_broker_facade(
            broker_id, _collect_gateway_extensions(gw, broker_id=broker_id)
        )
    if _session_kernel is not None:
        setattr(session, "kernel", _session_kernel)

    # Light resolver for doctor / resolve_name
    from domain.instruments.resolver import InstrumentResolver

    # Seed common liquid names for fuzzy doctor (extendable later from master)
    session._resolver = InstrumentResolver(  # type: ignore[attr-defined]
        known_symbols=[
            "RELIANCE",
            "TCS",
            "INFY",
            "HDFCBANK",
            "ICICIBANK",
            "SBIN",
            "NIFTY",
            "BANKNIFTY",
            "NIFTYBEES",
        ],
        default_exchange="NSE",
    )
    return session


def _collect_gateway_extensions(gateway: Any, *, broker_id: str = "") -> list[Any]:
    """Build broker Extension instances for BrokerFacade (instrument.broker.*)."""
    exts: list[Any] = []
    seen: set[str] = set()

    def _add(ext: Any) -> None:
        if ext is None:
            return
        key = getattr(ext, "name", None) or type(ext).__name__
        if key in seen:
            return
        seen.add(str(key))
        exts.append(ext)

    if broker_id:
        try:
            from infrastructure.adapter_factory import get_broker_extension_classes

            for cls in get_broker_extension_classes(broker_id):
                try:
                    _add(cls(gateway))
                except Exception:
                    continue
        except Exception:
            pass

    registry = getattr(gateway, "extension_registry", None)
    if registry is not None and hasattr(registry, "all"):
        try:
            for ext in registry.all():
                _add(ext)
        except Exception:
            pass
    get_ext = getattr(gateway, "get_extension", None)
    if callable(get_ext):
        for name in (
            "depth_20",
            "depth_200",
            "depth_30",
            "depth20",
            "depth200",
            "depth30",
            "news",
            "super_order",
            "forever_order",
        ):
            try:
                _add(get_ext(name))
            except Exception:
                continue
    return exts


def _ensure_broker_registered(broker_id: str) -> None:
    """Import broker package so self-registration runs."""
    if broker_id == "dhan":
        import brokers.dhan  # noqa: F401
    elif broker_id == "upstox":
        import brokers.upstox  # noqa: F401
    elif broker_id == "paper":
        import brokers.paper  # noqa: F401
    elif broker_id == "datalake":
        pass
    else:
        # Still try import path for unknown — gateway_factory will raise
        pass


# Public aliases
connect = open_session
