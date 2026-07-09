"""Unified broker diagnostics dashboard.

Phase 5: Uses :func:`cli.services.broker_registry.create_gateway` and
:func:`cli.services.broker_registry.list_available_brokers` to produce a
comprehensive, broker-agnostic diagnostics report.

Phase 4.4 (2026-06-21): Parallel execution of independent diagnostic checks
using ThreadPoolExecutor for 40-60% speedup.

Phase P4-2 (2026-06-22): Refactored using Strategy pattern — each diagnostic
check is now an independent ``CheckStrategy`` that can be tested, composed,
and executed in parallel.

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
from typing import Any

from rich.console import Console

from cli.commands.doctor.checks import CheckResult, CheckStrategy
from cli.commands.doctor.orchestrator import CheckOrchestrator, SectionResult
from cli.commands.doctor.renderer import ResultRenderer, _status_str
from cli.commands.doctor.strategies import (
    ActiveBrokerCheck,
    AuthLiveProbeCheck,
    AuthenticatedReadinessCheck,
    BrokerRegistryCheck,
    GatewayCreationCheck,
    HTTPObservabilityCheck,
    InstrumentCatalogCheck,
    LifecycleCheck,
    MarketDataCheck,
    OMSRiskManagerCheck,
    OrderAPICheck,
    PortfolioCheck,
)
from cli.services.broker_service import BrokerService

logger = logging.getLogger(__name__)

# Re-export for backward compatibility
__all__ = [
    "CheckOrchestrator",
    "CheckResult",
    "CheckStrategy",
    "CheckStrategy",
    "ResultRenderer",
    "_check_active_broker",
    "_check_broker_registry",
    "_check_gateway_creation",
    "_check_http_observability",
    "_check_instrument_catalog",
    "_check_lifecycle",
    "_check_market_data",
    "_check_oms_risk_manager",
    "_check_order_api",
    "_check_portfolio",
    "_render_table",
    "_run_checks_in_parallel",
    "_status_str",
    "run",
    "run_doctor",
]


def _render_table(
    title: str,
    results: list[CheckResult],
    console: Console,
    *,
    show_header: bool = True,
) -> None:
    """Render a diagnostics table for a group of checks.

    Backward-compatible wrapper around ResultRenderer.
    """
    renderer = ResultRenderer(console)
    renderer.render_section(title, results, show_header=show_header)


def _run_checks_in_parallel(
    checks: list[tuple[str, Any]],
    max_workers: int = 4,
    timeout_per_check: int = 15,
) -> dict[str, list[CheckResult]]:
    """Run independent diagnostic checks in parallel.

    Backward-compatible wrapper around CheckOrchestrator.
    """

    class _LegacyAdapter:
        """Adapter that wraps a legacy check function as a CheckStrategy."""

        def __init__(self, fn: Any):
            self._fn = fn

        def execute(self, broker_service: BrokerService | None) -> list[CheckResult]:
            return self._fn()

    adapted = [(name, _LegacyAdapter(fn)) for name, fn in checks]
    orchestrator = CheckOrchestrator(adapted, max_workers, timeout_per_check)
    section_results = orchestrator.run_all(None)

    return {name: sr.results for name, sr in section_results.items()}


# ═══════════════════════════════════════════════════════════════════════════
# Legacy check functions — delegate to strategy classes for backward compat
# ═══════════════════════════════════════════════════════════════════════════


def _check_broker_registry() -> list[CheckResult]:
    """Check all registered brokers and their env file status."""
    return BrokerRegistryCheck().execute(None)


def _check_gateway_creation() -> list[CheckResult]:
    """Attempt gateway creation via ``create_gateway()`` for each registered broker."""
    return GatewayCreationCheck().execute(None)


def _check_active_broker(broker_service: BrokerService) -> list[CheckResult]:
    """Report active broker identity and capabilities."""
    return ActiveBrokerCheck().execute(broker_service)


def _check_instrument_catalog(broker_service: BrokerService) -> list[CheckResult]:
    """Check instrument catalog loading and stats."""
    return InstrumentCatalogCheck().execute(broker_service)


def _check_market_data(
    broker_service: BrokerService,
    quick_mode: bool = False,
) -> list[CheckResult]:
    """Test quote, depth, and historical data endpoints."""
    return MarketDataCheck(quick_mode=quick_mode).execute(broker_service)


def _check_order_api(broker_service: BrokerService) -> list[CheckResult]:
    """Check order book and trade book API endpoints."""
    return OrderAPICheck().execute(broker_service)


def _check_portfolio(broker_service: BrokerService) -> list[CheckResult]:
    """Check positions, holdings, and funds balance."""
    return PortfolioCheck().execute(broker_service)


def _check_lifecycle(broker_service: BrokerService) -> list[CheckResult]:
    """Check every ManagedService registered with the LifecycleManager."""
    return LifecycleCheck().execute(broker_service)


def _check_oms_risk_manager(broker_service: BrokerService) -> list[CheckResult]:
    """Check OMS RiskManager state: kill-switch, daily PnL, resets."""
    return OMSRiskManagerCheck().execute(broker_service)


def _check_http_observability(broker_service: BrokerService) -> list[CheckResult]:
    """Check the HTTP observability server (/healthz, /readyz, /metrics)."""
    return HTTPObservabilityCheck().execute(broker_service)


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
    time.monotonic()

    console.print()
    console.print("[bold cyan]╔═══════════════════════════════════════════════════╗[/bold cyan]")
    console.print("[bold cyan]║    TradeXV2 Unified Broker Diagnostics Report     ║[/bold cyan]")
    if parallel_mode:
        console.print(
            "[bold cyan]║         ⚡ Parallel Execution Mode Enabled          ║[/bold cyan]"
        )
    console.print("[bold cyan]╚═══════════════════════════════════════════════════╝[/bold cyan]")
    console.print()

    renderer = ResultRenderer(console)

    # Section 1: Broker Registration & Environment (must run first — sequential)
    broker_results = BrokerRegistryCheck().execute(None)
    renderer.render_section("⚙️  Broker Registration & Environment", broker_results)

    auth_results = AuthenticatedReadinessCheck().execute(broker_service)
    renderer.render_section("🔐 Authenticated Readiness", auth_results)

    # Define independent checks with their display titles
    check_strategies: list[tuple[str, str, Any]] = [
        ("Gateway Creation", "🔧 Gateway Creation (create_gateway)", GatewayCreationCheck()),
        ("Active Broker", "🔌 Active Broker Identity", ActiveBrokerCheck()),
        ("Instrument Catalog", "📚 Instrument Catalog", InstrumentCatalogCheck()),
        ("Market Data", "📊 Market Data Endpoints", MarketDataCheck(quick_mode=quick_mode)),
        ("Order API", "📝 Order & Trade API", OrderAPICheck()),
        ("Portfolio", "💰 Portfolio Sync", PortfolioCheck()),
        ("Lifecycle", "🔋 Lifecycle Health", LifecycleCheck()),
        ("Risk Manager", "🛡️  OMS RiskManager", OMSRiskManagerCheck()),
        ("HTTP Observability", "🌐 HTTP Observability", HTTPObservabilityCheck()),
    ]

    if parallel_mode:
        console.print("[dim]⚡ Running checks in parallel...[/dim]\n")

        # Run independent checks in parallel
        orchestrator_checks = [(name, strategy) for name, _, strategy in check_strategies]
        orchestrator = CheckOrchestrator(orchestrator_checks, max_workers=4, timeout_per_check=15)
        parallel_results: dict[str, SectionResult] = orchestrator.run_all(broker_service)

        # Render results in order
        for key, title, _ in check_strategies:
            if key in parallel_results:
                renderer.render_section(title, parallel_results[key].results)

        # Collect all results for summary
        gw_results = parallel_results.get("Gateway Creation", SectionResult("", [])).results
        active_results = parallel_results.get("Active Broker", SectionResult("", [])).results
        inst_results = parallel_results.get("Instrument Catalog", SectionResult("", [])).results
        md_results = parallel_results.get("Market Data", SectionResult("", [])).results
        order_results = parallel_results.get("Order API", SectionResult("", [])).results
        portfolio_results = parallel_results.get("Portfolio", SectionResult("", [])).results
        lifecycle_results = parallel_results.get("Lifecycle", SectionResult("", [])).results
        risk_results = parallel_results.get("Risk Manager", SectionResult("", [])).results
        http_results = parallel_results.get("HTTP Observability", SectionResult("", [])).results

    else:
        # Sequential execution (original behavior)
        gw_results = GatewayCreationCheck().execute(None)
        renderer.render_section("🔧 Gateway Creation (create_gateway)", gw_results)

        active_results = ActiveBrokerCheck().execute(broker_service)
        renderer.render_section("🔌 Active Broker Identity", active_results)

        inst_results = InstrumentCatalogCheck().execute(broker_service)
        renderer.render_section("📚 Instrument Catalog", inst_results)

        md_results = MarketDataCheck(quick_mode=quick_mode).execute(broker_service)
        renderer.render_section("📊 Market Data Endpoints", md_results)

        order_results = OrderAPICheck().execute(broker_service)
        renderer.render_section("📝 Order & Trade API", order_results)

        portfolio_results = PortfolioCheck().execute(broker_service)
        renderer.render_section("💰 Portfolio Sync", portfolio_results)

        lifecycle_results = LifecycleCheck().execute(broker_service)
        renderer.render_section("🔋 Lifecycle Health", lifecycle_results)

        risk_results = OMSRiskManagerCheck().execute(broker_service)
        renderer.render_section("🛡️  OMS RiskManager", risk_results)

        http_results = HTTPObservabilityCheck().execute(broker_service)
        renderer.render_section("🌐 HTTP Observability", http_results)

    # Summary row
    all_results = (
        broker_results
        + auth_results
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

    renderer.render_summary(all_results)


def run_auth_doctor(
    broker_service: BrokerService,
    console: Console,
    *,
    force_refresh: bool = False,
    broker: str | None = None,
) -> None:
    """Auth-only diagnostics: probe with existing token; mint only if --force-refresh.

    Default is **probe-only** (funds/profile). Never generates TOTP unless
    ``force_refresh`` is True (then at most one mint after token rejection).
    """
    console.print()
    console.print("[bold cyan]TradeXV2 Auth Doctor[/bold cyan]")
    mode = "force-refresh (mint only if rejected)" if force_refresh else "probe-only (no TOTP)"
    console.print(f"[dim]Mode: {mode}[/dim]")
    console.print()

    renderer = ResultRenderer(console)
    check = AuthLiveProbeCheck(force_refresh=force_refresh, broker=broker)
    results = check.execute(broker_service)
    renderer.render_section("🔐 Live Auth Probe", results)
    renderer.render_summary(results)


def run(args: list[str], broker_service: BrokerService, console: Console) -> None:
    """Entry point for doctor subcommand.

    Supports optional flags:
      auth            Auth-only probe (no full diagnostics)
      --force-refresh With auth: allow one TOTP mint if probe rejects token
      --broker NAME   Run diagnostics for a specific broker
      --quick         Skip slower checks (depth, history)
      --parallel      Run independent checks in parallel (40-60% faster)
    """
    broker_override: str | None = None
    quick_mode = False
    parallel_mode = False
    auth_only = False
    force_refresh = False

    i = 0
    while i < len(args):
        if args[i] in ("auth", "--auth"):
            auth_only = True
            i += 1
        elif args[i] == "--force-refresh":
            force_refresh = True
            i += 1
        elif args[i] == "--broker" and i + 1 < len(args):
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

    if auth_only:
        run_auth_doctor(
            broker_service,
            console,
            force_refresh=force_refresh,
            broker=broker_override,
        )
        return

    if force_refresh and not auth_only:
        console.print(
            "[yellow]--force-refresh only applies with `doctor auth`; ignoring.[/yellow]"
        )

    run_doctor(broker_service, console, quick_mode=quick_mode, parallel_mode=parallel_mode)
