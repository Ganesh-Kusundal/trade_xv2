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

import logging
import uuid
from pathlib import Path
from typing import Any

from domain.connect_errors import (
    AUTH_FAILED,
    ENG_011,
    GATEWAY_FAILED,
    OMS_REQUIRED,
    UNKNOWN_BROKER,
    ConnectError,
)
from domain.session_status import (
    MODE_SIM,
    MODE_TRADE,
    PHASE_READY_MARKET,
    PHASE_READY_TRADE,
    SessionStatus,
)
from domain.universe import Session as DomainSession
from infrastructure.broker_plugin import ensure_core_plugins, get_broker_plugin
from runtime.broker_discovery import discover_broker_plugins
from runtime.wire_runtime_hooks import wire_runtime_hooks

# ── Extracted responsibility modules ──────────────────────────────────
# These keep the composition root focused. The private ``_`` aliases below
# preserve backward compatibility for callers/tests that reference the old
# names on ``tradex.session`` (and patch them there).
from tradex.broker_registry import ensure_registered as _ensure_broker_registered
from tradex.broker_selftest import is_enabled as _broker_selftest_enabled, run as _run_broker_selftest
from tradex.gateway_extensions import collect as _collect_gateway_extensions
from tradex.session_mode import (
    is_live as _is_live,
    normalize_mode as _normalize_mode,
)
from tradex.session_recorder import (
    is_enabled as _session_recording_enabled,
    maybe_start as _maybe_start_session_recorder,
)

logger = logging.getLogger(__name__)


def open_session(
    broker: str = "paper",
    *,
    mode: str | None = None,
    provider: Any | None = None,
    event_bus: Any | None = None,
    gateway: Any | None = None,
    execution_provider: Any | None = None,
    order_service: Any | None = None,
    broker_service: Any | None = None,
    use_oms: bool = True,
    env_path: str | Path | None = None,
    load_instruments: bool = True,
    profile: str | None = None,  # reserved for future config profiles
    run_selftest: bool | None = None,
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
    # Built-in metadata fallback (no broker imports), then entry-point discovery
    # so out-of-tree packages under ``tradex.brokers`` self-register (Part 4 §3.2).
    ensure_core_plugins()
    discover_broker_plugins()
    # Composition-root wiring: register the real OMS / domain-event /
    # trading-context factories so replay & backtest engines route through
    # the shared OMS kernel (zero-parity) instead of silently falling
    # back to PURE_SIM when a trading_context is supplied.
    wire_runtime_hooks()
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
    _lifecycle = None
    if gw is None and data is None and executor is None:
        from domain.ports.bootstrap import BootstrapStatus
        from infrastructure.gateway.factory import bootstrap_gateway

        # Live brokers own background services (TOTP refresh, WS streams).
        # Create a LifecycleManager here (composition root only) so the
        # gateway factory can register ManagedServices and we start them
        # deterministically — mirrors the TUI BrokerService model.
        if broker_id not in {"paper", "datalake"}:
            from infrastructure.lifecycle import LifecycleManager

            _lifecycle = LifecycleManager()

        try:
            boot = bootstrap_gateway(
                broker_id,
                env_path=env_path,
                load_instruments=load_instruments,
                event_bus=event_bus,
                require_authenticated=True,
                lifecycle=_lifecycle,
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

    # Start background services (TOTP refresh, WS streams) once the gateway
    # is live. Lifecycle is None for paper/datalake, so this is a no-op there.
    if _lifecycle is not None:
        try:
            _lifecycle.start_all()
        except Exception as exc:  # defensive — never block connect on lifecycle
            import logging

            logging.getLogger(__name__).warning(
                "session lifecycle start failed for %s: %s", broker_id, exc
            )

    # P0-I: register quota profiles + router whenever we have a concrete gateway
    if gw is not None and broker_id not in {"datalake"}:
        from runtime.session_infra import wire_gateway_for_session

        try:
            _session_kernel = wire_gateway_for_session(gw, broker_id)
        except Exception as exc:  # defensive — never block connect on kernel wire
            import logging

            logging.getLogger(__name__).warning(
                "session kernel wire failed for %s: %s", broker_id, exc
            )

    # ── Data provider ─────────────────────────────────────────────────
    # Paper is self-registered in infrastructure.adapter_factory (via
    # ensure_broker_module above), so it resolves through the same registry
    # path as dhan/upstox — no concrete broker import by name.
    if data is None:
        if gw is not None:
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
    # Paper is self-registered in infrastructure.adapter_factory (via
    # ensure_broker_module above), so it resolves through the same registry
    # path as dhan/upstox — no concrete broker import by name.
    if executor is None and gw is not None and broker_id != "datalake":
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

    if oms is None and use_oms and orders_wanted:
        # ADR-017: trade mode with process BrokerService uses runtime.factory.build.
        if (
            resolved_mode == MODE_TRADE
            and broker_service is not None
            and executor is not None
        ):
            from runtime.factory import build as build_runtime

            runtime = build_runtime(
                broker_service,
                mode="trade",
                broker=broker_id,
            )
            oms = runtime.oms_service
            if event_bus is None:
                event_bus = runtime.event_bus
            if gw is None:
                gw = runtime.gateway
            setattr(runtime, "_tradex_session_delegate", True)
        elif executor is not None:
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

            # Wire the OMS order_manager back to the PaperGateway so it can
            # route orders through the OMS (gateway was created before OMS).
            if gw is not None and hasattr(gw, "_orders") and oms is not None:
                om = getattr(oms, "order_manager", None) or getattr(oms, "_oms", None)
                if om is not None:
                    gw._orders._order_manager = om

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
    if _lifecycle is not None:
        # Attach so the session's close() stops background services (TOTP
        # refresh, WS streams) deterministically. setattr keeps the domain
        # layer free of lifecycle imports.
        setattr(session, "_lifecycle", _lifecycle)

    # ── CQRS dispatchers (ADR-012) ───────────────────────────────────
    # Build the CommandDispatcher / QueryDispatcher at the composition root so
    # SDK/CLI/API/UI all route intent + reads through one seam. The command
    # dispatcher wraps the OMS; the query dispatcher reads from the position
    # manager / analytics query executor. Both are optional (data-only mode).
    # (Dispatcher construction lives here, not in domain/application, to keep
    # the domain layer independent and avoid an application->runtime cycle.)
    from runtime.commands import (
        CommandDispatcher,
        HistoryCommandHandler,
        OrderCommandHandler,
        SubscribeCommandHandler,
        build_order_dispatcher,
    )
    from runtime.queries import (
        CandleQueryHandler,
        PortfolioQueryHandler,
        QueryDispatcher,
    )

    command_dispatcher = CommandDispatcher(event_bus=event_bus)
    order_command_fn = None
    if oms is not None:
        order_manager = getattr(oms, "order_manager", None)
        submit_fn = getattr(oms, "_submit_fn", None)
        if order_manager is not None:
            command_dispatcher.register_handler(
                OrderCommandHandler(order_manager, submit_fn=submit_fn)
            )
            # F7: single PlaceOrder mapping via build_order_dispatcher
            order_command_fn = build_order_dispatcher(
                order_manager, submit_fn=submit_fn, event_bus=event_bus
            )
    # Subscribe / history route through the session's DataProvider when present.
    if data is not None:
        command_dispatcher.register_handler(SubscribeCommandHandler(data))
        command_dispatcher.register_handler(HistoryCommandHandler(data))

    query_dispatcher = QueryDispatcher()
    position_manager = getattr(oms, "order_manager", None) if oms is not None else None
    if position_manager is None:
        from application.oms import PositionManager

        position_manager = PositionManager(event_bus=event_bus)
    query_dispatcher.register_handler(PortfolioQueryHandler(position_manager))
    try:
        from analytics.views.query_executor import QueryExecutor

        # Only register if the executor actually exposes a candle reader; the
        # analytics QueryExecutor is SQL-based and may not have get_candles.
        if hasattr(QueryExecutor, "get_candles"):
            query_dispatcher.register_handler(CandleQueryHandler(QueryExecutor))
        else:
            logger.debug("QueryDispatcher: analytics QueryExecutor has no get_candles; candles read-only skipped")
    except Exception:  # pragma: no cover - analytics optional at SDK layer
        logger.debug("QueryDispatcher: analytics QueryExecutor not wired (candles read-only)")

    session.attach_command_dispatcher(command_dispatcher)
    session.attach_query_dispatcher(query_dispatcher)

    if order_command_fn is not None:
        session.attach_order_command_fn(order_command_fn)

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
    # Opt-in SessionRecording (TRADEX_SESSION_RECORD=1); never blocks connect.
    _maybe_start_session_recorder(session, event_bus, session_id=trace_id)

    should_selftest = run_selftest if run_selftest is not None else _broker_selftest_enabled()
    if should_selftest and broker_id not in {"datalake"}:
        _run_broker_selftest(session, broker_id)

    return session


# Public aliases
connect = open_session
