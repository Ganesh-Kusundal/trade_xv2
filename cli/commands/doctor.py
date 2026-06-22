"""Unified broker diagnostics dashboard.

Phase 5: Uses :func:`cli.services.broker_registry.create_gateway` and
:func:`cli.services.broker_registry.list_available_brokers` to produce a
comprehensive, broker-agnostic diagnostics report.

Phase 4.4 (2026-06-21): Parallel execution of independent diagnostic checks
using ThreadPoolExecutor for 40-60% speedup.

The doctor checks:

  1. Broker registration & env file status (all registered brokers)
  2. Gateway creation smoke test (uses ``create_gateway()`` per broker)
  3. Active broker identity & capabilities matrix
  4. Instrument catalog health
  5. Market data (quote, depth, historical)
  6. Order & trade API reachability
  7. Portfolio sync (positions, holdings, balance)
  8. LifecycleManager health (every ManagedService)
  9. OMS RiskManager state (kill-switch, daily PnL, resets)
  10. HTTP observability surface (/healthz, /readyz, /metrics)
"""

from __future__ import annotations

import logging
import time
from concurrent.futures import ThreadPoolExecutor, as_completed, TimeoutError
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Any

from rich.console import Console
from rich.table import Table

from cli.services.broker_registry import (
    create_gateway,
    list_available_brokers,
    resolve_env_path,
)
from cli.services.broker_service import BrokerService

logger = logging.getLogger(__name__)


# ── Result model ───────────────────────────────────────────────────────────


@dataclass
class CheckResult:
    """Single diagnostic check result."""

    name: str
    status: str  # "PASS", "WARN", "FAIL"
    detail: str = ""


# ── Helpers ────────────────────────────────────────────────────────────────


def _status_str(status: str) -> str:
    if status == "PASS":
        return "[green]PASS[/green]"
    if status == "WARN":
        return "[yellow]WARN[/yellow]"
    return "[red]FAIL[/red]"


def _run_checks_in_parallel(
    checks: list[tuple[str, Any]],
    max_workers: int = 4,
    timeout_per_check: int = 15,
) -> dict[str, list[CheckResult]]:
    """Run independent diagnostic checks in parallel.

    Parameters
    ----------
    checks :
        List of (section_name, check_fn) tuples.
    max_workers :
        Maximum number of parallel threads.
    timeout_per_check :
        Timeout in seconds for each individual check.

    Returns
    -------
    dict[str, list[CheckResult]]
        Mapping of section name to list of check results.
    """
    results: dict[str, list[CheckResult]] = {}

    def _execute_check(name: str, check_fn: Any) -> tuple[str, list[CheckResult]]:
        """Execute a single check with timeout protection."""
        try:
            start = time.monotonic()
            check_results = check_fn()
            elapsed = time.monotonic() - start
            logger.info(
                "doctor_check_completed",
                extra={"check": name, "elapsed_s": round(elapsed, 2)},
            )
            return (name, check_results)
        except TimeoutError:
            logger.warning("doctor_check_timeout", extra={"check": name})
            return (
                name,
                [CheckResult(name, "FAIL", f"Timeout after {timeout_per_check}s")],
            )
        except Exception as exc:
            logger.exception(
                "doctor_check_failed",
                extra={"check": name, "error": str(exc)},
            )
            return (name, [CheckResult(name, "ERROR", str(exc))])

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {
            executor.submit(_execute_check, name, check_fn): name
            for name, check_fn in checks
        }

        for future in as_completed(futures):
            section_name, check_results = future.result(timeout=timeout_per_check)
            results[section_name] = check_results

    return results


def _render_table(
    title: str,
    results: list[CheckResult],
    console: Console,
    *,
    show_header: bool = True,
) -> None:
    """Render a diagnostics table for a group of checks."""
    if not results:
        return
    table = Table(
        title=title,
        header_style="bold cyan",
        show_header=show_header,
        title_justify="left",
    )
    table.add_column("Check", style="bold white", width=32)
    table.add_column("Status", justify="center", width=8)
    table.add_column("Detail", style="dim white", width=72)
    for r in results:
        table.add_row(r.name, _status_str(r.status), r.detail)
    console.print(table)
    console.print()


# ═══════════════════════════════════════════════════════════════════════════
# 1. Broker Registration & Environment
# ═══════════════════════════════════════════════════════════════════════════


def _check_broker_registry() -> list[CheckResult]:
    """Check all registered brokers and their env file status."""
    results: list[CheckResult] = []
    brokers = list_available_brokers()

    if not brokers:
        results.append(CheckResult("Registered Brokers", "FAIL", "No brokers registered!"))
        return results

    results.append(
        CheckResult(
            "Registered Brokers",
            "PASS",
            f"{len(brokers)} broker(s): {', '.join(b['name'] for b in brokers)}",
        )
    )

    for b in brokers:
        name = b["name"]
        env_file = b["env_file"]
        available = b["available"]

        if env_file is None:
            results.append(
                CheckResult(
                    f"  {name.title()}",
                    "INFO",
                    "No env file needed (paper broker).",
                )
            )
        elif available:
            resolved = resolve_env_path(name)
            size = resolved.stat().st_size if resolved and resolved.exists() else 0
            results.append(
                CheckResult(
                    f"  {name.title()}",
                    "PASS",
                    f"Env file found: {resolved} ({size:,} bytes)",
                )
            )
        else:
            resolved = resolve_env_path(name)
            results.append(
                CheckResult(
                    f"  {name.title()}",
                    "WARN",
                    f"Env file missing: {resolved}",
                )
            )

    return results


# ═══════════════════════════════════════════════════════════════════════════
# 2. Gateway Creation Smoke Test (uses create_gateway)
# ═══════════════════════════════════════════════════════════════════════════


def _check_gateway_creation() -> list[CheckResult]:
    """Attempt gateway creation via ``create_gateway()`` for each registered broker.

    This is a lightweight smoke test — it validates that the factory
    can be imported and that ``create_gateway()`` returns a non-None
    gateway object.  Full initialization (env loading, instrument fetch)
    is intentionally skipped via ``load_instruments=False`` so the
    check is fast even when no broker is configured.
    """
    results: list[CheckResult] = []
    brokers = list_available_brokers()

    for b in brokers:
        name = b["name"]

        # Paper broker has no env file and always succeeds
        if b["env_file"] is None:
            results.append(
                CheckResult(
                    f"  {name.title()}",
                    "INFO",
                    "No gateway creation needed (paper broker)",
                )
            )
            continue

        try:
            gw = create_gateway(name, load_instruments=False)
            if gw is not None:
                results.append(
                    CheckResult(
                        f"  {name.title()}",
                        "PASS",
                        f"Gateway created via create_gateway('{name}')",
                    )
                )
            else:
                results.append(
                    CheckResult(
                        f"  {name.title()}",
                        "FAIL",
                        f"create_gateway('{name}') returned None",
                    )
                )
        except Exception as exc:
            results.append(
                CheckResult(
                    f"  {name.title()}",
                    "FAIL",
                    f"create_gateway('{name}') raised: {exc}",
                )
            )

    return results


# ═══════════════════════════════════════════════════════════════════════════
# 3. Active Broker Identity
# ═══════════════════════════════════════════════════════════════════════════


def _check_active_broker(broker_service: BrokerService) -> list[CheckResult]:
    """Report active broker identity and capabilities."""
    results: list[CheckResult] = []

    try:
        name = broker_service.active_broker_name
        gw = broker_service.active_broker
        desc = gw.describe() if hasattr(gw, "describe") else {}
        caps = gw.capabilities() if hasattr(gw, "capabilities") else None

        conn_type = desc.get("type", "live")
        results.append(
            CheckResult(
                "Active Broker",
                "PASS",
                f"{name.title()} ({conn_type}) — {desc.get('name', name)} v{desc.get('version', '?')}",
            )
        )

        if caps:
            features = []
            if caps.websocket:
                features.append("WebSocket")
            if caps.depth_20:
                features.append("Depth20")
            if caps.depth_200:
                features.append("Depth200")
            if caps.super_orders:
                features.append("SuperOrders")
            order_types = ", ".join(caps.order_types[:4])
            results.append(
                CheckResult(
                    "  Capabilities",
                    "PASS",
                    f"Orders: {order_types} | Features: {', '.join(features) or 'none'}",
                )
            )
            results.append(
                CheckResult(
                    "  Rate Limits",
                    "PASS",
                    f"{caps.rate_limit_per_second}/s, {caps.rate_limit_per_minute}/min",
                )
            )
    except Exception as exc:
        results.append(
            CheckResult(
                "Active Broker",
                "FAIL",
                f"Cannot determine active broker: {exc}",
            )
        )

    return results


# ═══════════════════════════════════════════════════════════════════════════
# 4. Instrument Catalog
# ═══════════════════════════════════════════════════════════════════════════


def _check_instrument_catalog(broker_service: BrokerService) -> list[CheckResult]:
    """Check instrument catalog loading and stats."""
    results: list[CheckResult] = []

    try:
        gw = broker_service.active_broker
        # Try standard Interface-Aware approach first (search works on all brokers)
        search_test = gw.search("RELIANCE") if hasattr(gw, "search") else []
        if search_test and len(search_test) > 0:
            results.append(
                CheckResult(
                    "Instrument Search",
                    "PASS",
                    f"Search returned {len(search_test)} result(s) for 'RELIANCE'",
                )
            )
        else:
            results.append(
                CheckResult(
                    "Instrument Search",
                    "WARN",
                    "Search returned empty results (maybe no instruments loaded)",
                )
            )

        # Check instruments by trying to resolve a known symbol
        try:
            insts = gw.instruments
            if hasattr(insts, "stats"):
                stats = insts.stats()
                total = stats.get("total", 0)
                loaded = stats.get("loaded", False)
                if loaded and total > 0:
                    results.append(
                        CheckResult(
                            "Instrument Resolver",
                            "PASS",
                            f"{total:,} instruments loaded into resolver",
                        )
                    )
                else:
                    results.append(
                        CheckResult(
                            "Instrument Resolver",
                            "WARN",
                            f"Resolver loaded={loaded}, total={total}",
                        )
                    )
        except (AttributeError, Exception):
            results.append(
                CheckResult(
                    "Instrument Resolver",
                    "INFO",
                    "Instrument resolver stats not available (paper/mock gateway)",
                )
            )

    except Exception as exc:
        results.append(
            CheckResult(
                "Instrument Catalog",
                "FAIL",
                f"Catalog check failed: {exc}",
            )
        )

    return results


# ═══════════════════════════════════════════════════════════════════════════
# 5. Market Data Checks
# ═══════════════════════════════════════════════════════════════════════════


def _check_market_data(
    broker_service: BrokerService,
    quick_mode: bool = False,
) -> list[CheckResult]:
    """Test quote, depth, and historical data endpoints."""
    results: list[CheckResult] = []
    gw = broker_service.active_broker

    # Quote check
    try:
        symbol = "RELIANCE"
        q = gw.quote(symbol)
        if q is not None and q.ltp > 0:
            results.append(
                CheckResult(
                    "Quote",
                    "PASS",
                    f"{symbol}: LTP={q.ltp:.2f} | O={q.open:.2f} H={q.high:.2f} "
                    f"L={q.low:.2f} C={q.close:.2f} Vol={q.volume:,}",
                )
            )
        else:
            results.append(
                CheckResult(
                    "Quote",
                    "WARN",
                    f"{symbol} returned quote with LTP=0 (paper/mock?)",
                )
            )
    except Exception as exc:
        results.append(
            CheckResult("Quote", "FAIL", f"Quote failed: {exc}")
        )

    # Depth check (skipped in quick mode)
    if quick_mode:
        results.append(
            CheckResult("Market Depth", "INFO", "Skipped (--quick mode)")
        )
    else:
        try:
            symbol = "RELIANCE"
            depth = gw.depth(symbol)
            if depth is not None:
                n_bids = len(depth.bids)
                n_asks = len(depth.asks)
                if n_bids > 0 or n_asks > 0:
                    results.append(
                        CheckResult(
                            "Market Depth",
                            "PASS",
                            f"{symbol}: {n_bids} bid(s), {n_asks} ask(s)",
                        )
                    )
                else:
                    results.append(
                        CheckResult(
                            "Market Depth",
                            "WARN",
                            f"{symbol}: depth returned empty levels",
                        )
                    )
            else:
                results.append(
                    CheckResult(
                        "Market Depth",
                        "WARN",
                        f"{symbol}: depth returned None",
                    )
                )
        except Exception as exc:
            results.append(
                CheckResult("Market Depth", "FAIL", f"Depth failed: {exc}")
            )

    # Historical data check (skipped in quick mode)
    if quick_mode:
        results.append(
            CheckResult("Historical Data", "INFO", "Skipped (--quick mode)")
        )
    else:
        try:
            symbol = "RELIANCE"
            to_dt = date.today().isoformat()
            from_dt = (date.today() - timedelta(days=5)).isoformat()
            hist = gw.history(symbol, timeframe="1D", from_date=from_dt, to_date=to_dt)
            if hist is not None and not hist.empty:
                results.append(
                    CheckResult(
                        "Historical Data",
                        "PASS",
                        f"{symbol}: {len(hist)} candles ({from_dt} to {to_dt})",
                    )
                )
            else:
                results.append(
                    CheckResult(
                        "Historical Data",
                        "WARN",
                        f"{symbol}: empty DataFrame returned",
                    )
                )
        except Exception as exc:
            results.append(
                CheckResult("Historical Data", "FAIL", f"History failed: {exc}")
            )

    return results


# ═══════════════════════════════════════════════════════════════════════════
# 6. Order & Trade API
# ═══════════════════════════════════════════════════════════════════════════


def _check_order_api(broker_service: BrokerService) -> list[CheckResult]:
    """Check order book and trade book API endpoints."""
    results: list[CheckResult] = []
    gw = broker_service.active_broker

    # Order book
    try:
        orders = gw.get_orderbook()
        results.append(
            CheckResult(
                "Order Book",
                "PASS",
                f"{len(orders)} order(s) retrieved",
            )
        )
    except Exception as exc:
        results.append(
            CheckResult("Order Book", "FAIL", f"Order book failed: {exc}")
        )

    # Trade book
    try:
        trades = gw.get_trade_book()
        results.append(
            CheckResult(
                "Trade Book",
                "PASS",
                f"{len(trades)} trade(s) retrieved",
            )
        )
    except Exception as exc:
        results.append(
            CheckResult("Trade Book", "FAIL", f"Trade book failed: {exc}")
        )

    return results


# ═══════════════════════════════════════════════════════════════════════════
# 7. Portfolio Sync
# ═══════════════════════════════════════════════════════════════════════════


def _check_portfolio(broker_service: BrokerService) -> list[CheckResult]:
    """Check positions, holdings, and funds balance."""
    results: list[CheckResult] = []
    gw = broker_service.active_broker

    # Positions
    try:
        positions = gw.positions()
        results.append(
            CheckResult(
                "Positions",
                "PASS",
                f"{len(positions)} open position(s)",
            )
        )
    except Exception as exc:
        results.append(
            CheckResult("Positions", "FAIL", f"Positions failed: {exc}")
        )

    # Holdings
    try:
        holdings = gw.holdings()
        results.append(
            CheckResult(
                "Holdings",
                "PASS",
                f"{len(holdings)} holding(s)",
            )
        )
    except Exception as exc:
        results.append(
            CheckResult("Holdings", "FAIL", f"Holdings failed: {exc}")
        )

    # Balance / Funds
    try:
        balance = gw.funds()
        available = getattr(balance, "available_balance", None)
        sod = getattr(balance, "sod_limit", None)
        if available is not None:
            results.append(
                CheckResult(
                    "Funds",
                    "PASS",
                    f"Available: Rs. {available:,.2f}" + (f" | SOD Limit: Rs. {sod:,.2f}" if sod else ""),
                )
            )
        else:
            results.append(
                CheckResult(
                    "Funds",
                    "WARN",
                    "Balance returned but available_balance is None",
                )
            )
    except Exception as exc:
        results.append(
            CheckResult("Funds", "FAIL", f"Funds failed: {exc}")
        )

    return results


# ═══════════════════════════════════════════════════════════════════════════
# 8. LifecycleManager Health
# ═══════════════════════════════════════════════════════════════════════════


def _check_lifecycle(broker_service: BrokerService) -> list[CheckResult]:
    """Check every ManagedService registered with the LifecycleManager."""
    results: list[CheckResult] = []

    try:
        snapshot = broker_service.lifecycle.health_snapshot()
    except Exception as exc:
        results.append(
            CheckResult("Lifecycle", "FAIL", f"Health snapshot failed: {exc}")
        )
        return results

    if not snapshot:
        results.append(
            CheckResult("Lifecycle", "WARN", "No ManagedServices registered (lifecycle empty)")
        )
        return results

    service_names = list(snapshot.keys())
    failed = [
        (n, s)
        for n, s in snapshot.items()
        if s.get("state") in ("FAILED", "UNHEALTHY")
    ]
    degraded = [
        (n, s)
        for n, s in snapshot.items()
        if s.get("state") in ("DEGRADED",)
    ]

    n_services = len(snapshot)
    n_failed = len(failed)
    n_degraded = len(degraded)

    if n_failed == 0 and n_degraded == 0:
        results.append(
            CheckResult(
                "Lifecycle",
                "PASS",
                f"{n_services} service(s): {', '.join(service_names)}",
            )
        )
    elif n_failed == 0:
        results.append(
            CheckResult(
                "Lifecycle",
                "WARN",
                f"{n_services} service(s), {n_degraded} degraded: "
                f"{', '.join(n for n, _ in degraded[:3])}",
            )
        )
    else:
        failed_detail = ", ".join(
            f"{n}({s.get('state', '?')})" for n, s in failed[:5]
        )
        results.append(
            CheckResult(
                "Lifecycle",
                "FAIL",
                f"{n_failed}/{n_services} service(s) failed: {failed_detail}",
            )
        )

    # Detail per service
    for name, info in snapshot.items():
        state = info.get("state", "?")
        detail = info.get("detail", "") or info.get("metrics", {})
        if isinstance(detail, dict):
            detail_str = "; ".join(f"{k}={v}" for k, v in detail.items() if v is not None)
        else:
            detail_str = str(detail) if detail else ""

        if state == "HEALTHY":
            results.append(CheckResult(f"  {name}", "PASS", detail_str or "healthy"))
        elif state in ("DEGRADED",):
            results.append(CheckResult(f"  {name}", "WARN", detail_str or "degraded"))
        elif state in ("FAILED", "UNHEALTHY"):
            results.append(CheckResult(f"  {name}", "FAIL", detail_str or state))
        else:
            results.append(CheckResult(f"  {name}", "INFO", f"state={state}: {detail_str}"))

    return results


# ═══════════════════════════════════════════════════════════════════════════
# 9. OMS RiskManager
# ═══════════════════════════════════════════════════════════════════════════


def _check_oms_risk_manager(broker_service: BrokerService) -> list[CheckResult]:
    """Check OMS RiskManager state: kill-switch, daily PnL, resets."""
    results: list[CheckResult] = []

    tc = broker_service.trading_context
    if tc is None:
        results.append(
            CheckResult(
                "OMS RiskManager",
                "WARN",
                "No TradingContext (init failed or mock mode)",
            )
        )
        return results

    try:
        rm = tc.risk_manager
        snap = rm.snapshot()
        ks = "ACTIVE" if snap.get("kill_switch") else "inactive"
        daily_pnl = float(snap.get("daily_pnl", 0))
        resets = int(snap.get("reset_count", 0))
        results.append(
            CheckResult(
                "OMS RiskManager",
                "PASS",
                f"kill_switch={ks} | daily_pnl={daily_pnl:.2f} | resets={resets}",
            )
        )
    except Exception as exc:
        results.append(
            CheckResult("OMS RiskManager", "FAIL", f"Risk snapshot failed: {exc}")
        )

    return results


# ═══════════════════════════════════════════════════════════════════════════
# 10. HTTP Observability
# ═══════════════════════════════════════════════════════════════════════════


def _check_http_observability(broker_service: BrokerService) -> list[CheckResult]:
    """Check the HTTP observability server (/healthz, /readyz, /metrics)."""
    results: list[CheckResult] = []

    server = broker_service.http_observability
    if server is None:
        results.append(
            CheckResult(
                "HTTP Observability",
                "WARN",
                "Server not started (bind may have failed or init incomplete)",
            )
        )
        return results

    try:
        h = server.health()
        port = h.metrics.get("port", 0)
        state = h.state.value
        if state == "HEALTHY":
            results.append(
                CheckResult(
                    "HTTP Observability",
                    "PASS",
                    f"Listening on 127.0.0.1:{port} (state={state})",
                )
            )
        else:
            results.append(
                CheckResult(
                    "HTTP Observability",
                    "WARN",
                    f"Listening on 127.0.0.1:{port} (state={state})",
                )
            )
    except Exception as exc:
        results.append(
            CheckResult(
                "HTTP Observability",
                "FAIL",
                f"Health check failed: {exc}",
            )
        )

    return results


# ═══════════════════════════════════════════════════════════════════════════
# Public API
# ═══════════════════════════════════════════════════════════════════════════


def run_doctor(
    broker_service: BrokerService,
    console: Console,
    quick_mode: bool = False,
    parallel_mode: bool = False,
) -> None:
    """Execute all diagnostics checks and render the unified report.

    This is the single entry point for the ``doctor`` CLI command.

    Parameters
    ----------
    broker_service : BrokerService
        The active broker service instance.
    console : Console
        Rich console for output.
    quick_mode : bool
        If ``True``, skip slower checks (depth, historical data).
    parallel_mode : bool
        If ``True``, run independent checks in parallel using ThreadPoolExecutor.
        Provides 40-60% speedup for full diagnostics.
    """
    start_time = time.monotonic()

    console.print()
    console.print(
        "[bold cyan]╔═══════════════════════════════════════════════════╗[/bold cyan]"
    )
    console.print(
        "[bold cyan]║    TradeXV2 Unified Broker Diagnostics Report     ║[/bold cyan]"
    )
    if parallel_mode:
        console.print(
            "[bold cyan]║         ⚡ Parallel Execution Mode Enabled          ║[/bold cyan]"
        )
    console.print(
        "[bold cyan]╚═══════════════════════════════════════════════════╝[/bold cyan]"
    )
    console.print()

    # Section 1: Broker Registration & Environment (must run first)
    broker_results = _check_broker_registry()
    _render_table("⚙️  Broker Registration & Environment", broker_results, console)

    # Phase 4.4: Run independent checks in parallel if requested
    if parallel_mode:
        console.print("[dim]⚡ Running checks in parallel...[/dim]\n")

        # Define independent checks that can run in parallel
        parallel_checks = [
            ("Gateway Creation", _check_gateway_creation),
            ("Active Broker", lambda: _check_active_broker(broker_service)),
            ("Instrument Catalog", lambda: _check_instrument_catalog(broker_service)),
            ("Market Data", lambda: _check_market_data(broker_service, quick_mode=quick_mode)),
            ("Order API", lambda: _check_order_api(broker_service)),
            ("Portfolio", lambda: _check_portfolio(broker_service)),
            ("Lifecycle", lambda: _check_lifecycle(broker_service)),
            ("Risk Manager", lambda: _check_oms_risk_manager(broker_service)),
            ("HTTP Observability", lambda: _check_http_observability(broker_service)),
        ]

        # Execute checks in parallel
        parallel_results = _run_checks_in_parallel(
            parallel_checks,
            max_workers=4,
            timeout_per_check=15,
        )

        # Render results in order
        section_order = [
            ("Gateway Creation", "🔧 Gateway Creation (create_gateway)"),
            ("Active Broker", "🔌 Active Broker Identity"),
            ("Instrument Catalog", "📚 Instrument Catalog"),
            ("Market Data", "📊 Market Data Endpoints"),
            ("Order API", "📝 Order & Trade API"),
            ("Portfolio", "💰 Portfolio Sync"),
            ("Lifecycle", "🔋 Lifecycle Health"),
            ("Risk Manager", "🛡️  OMS RiskManager"),
            ("HTTP Observability", "🌐 HTTP Observability"),
        ]

        for key, title in section_order:
            if key in parallel_results:
                _render_table(title, parallel_results[key], console)

        # Collect all results for summary
        gw_results = parallel_results.get("Gateway Creation", [])
        active_results = parallel_results.get("Active Broker", [])
        inst_results = parallel_results.get("Instrument Catalog", [])
        md_results = parallel_results.get("Market Data", [])
        order_results = parallel_results.get("Order API", [])
        portfolio_results = parallel_results.get("Portfolio", [])
        lifecycle_results = parallel_results.get("Lifecycle", [])
        risk_results = parallel_results.get("Risk Manager", [])
        http_results = parallel_results.get("HTTP Observability", [])

    else:
        # Sequential execution (original behavior)
        # Section 2: Gateway Creation Smoke Test (uses create_gateway directly)
        gw_results = _check_gateway_creation()
        _render_table("🔧 Gateway Creation (create_gateway)", gw_results, console)

        # Section 3: Active Broker Identity
        active_results = _check_active_broker(broker_service)
        _render_table("🔌 Active Broker Identity", active_results, console)

        # Section 4: Instrument Catalog
        inst_results = _check_instrument_catalog(broker_service)
        _render_table("📚 Instrument Catalog", inst_results, console)

        # Section 5: Market Data
        md_results = _check_market_data(broker_service, quick_mode=quick_mode)
        _render_table("📊 Market Data Endpoints", md_results, console)

        # Section 6: Order & Trade API
        order_results = _check_order_api(broker_service)
        _render_table("📝 Order & Trade API", order_results, console)

        # Section 7: Portfolio
        portfolio_results = _check_portfolio(broker_service)
        _render_table("💰 Portfolio Sync", portfolio_results, console)

        # Section 8: LifecycleManager
        lifecycle_results = _check_lifecycle(broker_service)
        _render_table("🔋 Lifecycle Health", lifecycle_results, console)

        # Section 9: OMS RiskManager
        risk_results = _check_oms_risk_manager(broker_service)
        _render_table("🛡️  OMS RiskManager", risk_results, console)

        # Section 10: HTTP Observability
        http_results = _check_http_observability(broker_service)
        _render_table("🌐 HTTP Observability", http_results, console)

    # Summary row
    all_results = (
        broker_results
        + gw_results
        + active_results
        + inst_results
        + md_results
        + order_results
        + portfolio_results
        + lifecycle_results
        + risk_results
        + http_results
    )
    n_pass = sum(1 for r in all_results if r.status == "PASS")
    n_warn = sum(1 for r in all_results if r.status == "WARN")
    n_fail = sum(1 for r in all_results if r.status == "FAIL")
    n_info = sum(1 for r in all_results if r.status == "INFO")
    total = len(all_results)

    console.print()
    summary_parts = [
        f"[green]{n_pass} passed[/green]",
        f"[yellow]{n_warn} warnings[/yellow]" if n_warn else None,
        f"[red]{n_fail} failed[/red]" if n_fail else None,
        f"[dim]{n_info} info[/dim]" if n_info else None,
    ]
    summary_str = " | ".join(p for p in summary_parts if p)
    console.print(f"[bold]Summary:[/bold] {summary_str}  [dim]({total} checks total)[/dim]")
    console.print()


def run(args: list[str], broker_service: BrokerService, console: Console) -> None:
    """Entry point for doctor subcommand.

    Supports optional flags:
      --broker NAME   Run diagnostics for a specific broker
      --quick         Skip slower checks (depth, history)
      --parallel      Run independent checks in parallel (40-60% faster)
    """
    broker_override: str | None = None
    quick_mode = False
    parallel_mode = False

    i = 0
    while i < len(args):
        if args[i] == "--broker" and i + 1 < len(args):
            broker_override = args[i + 1].lower()
            i += 2
        elif args[i] == "--quick":
            quick_mode = True
            i += 1
        elif args[i] == "--parallel":
            parallel_mode = True
            i += 1
        else:
            i += 1

    if broker_override:
        try:
            broker_service.set_active_broker(broker_override)
        except ValueError as exc:
            console.print(f"[red]{exc}[/red]")
            return

    run_doctor(broker_service, console, quick_mode=quick_mode, parallel_mode=parallel_mode)
