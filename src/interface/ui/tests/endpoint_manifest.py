"""Endpoint manifest for `./tradex` CLI coverage.

Single source of truth for every testable CLI invocation. The
manifest drives:

* ``test_command_registry.py`` — registry contract checks
* ``test_cli_endpoint_matrix.py`` — subprocess smoke tests
* ``test_commands.py`` — live_readonly integration expansion
* ``test_order_sandbox_integration.py`` — sandbox order flow

Adding a new CLI command?  Add an entry here or its parent tier
test will silently miss coverage.

Tier definitions
----------------
* ``offline``     — no broker auth required; runs in default CI.
* ``live_readonly`` — requires ``.env.local`` Dhan creds + valid
  token; skipped otherwise.
* ``sandbox``     — places/cancels real orders; requires
  ``DHAN_INTEGRATION=1`` + valid creds; never in default CI.
* ``destructive`` — explicit confirm/reset paths; not exercised by
  the automated matrix, listed here for completeness.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

Tier = Literal["offline", "live_readonly", "sandbox", "destructive"]


@dataclass(frozen=True)
class CliEndpoint:
    """One testable CLI invocation."""

    id: str
    argv: list[str]
    tier: Tier
    expect_exit: int
    expect_stdout_substr: str | None = None
    timeout_s: int = 30
    description: str = ""
    capability_id: str | None = None
    # Some endpoints must run with mocked brokers (handler-level T2
    # tests) — flag here to opt them out of the live subprocess tier
    # even though their top-level command is on the dispatch table.
    no_subprocess: bool = field(default=False)


# ── offline endpoints (run in default CI) ─────────────────────────────
OFFLINE_ENDPOINTS: list[CliEndpoint] = [
    CliEndpoint("help_no_args", [], "offline", 0, "TradeXV2 CLI", 10),
    CliEndpoint("help_dash", ["--help"], "offline", 0, "TradeXV2 CLI", 10),
    CliEndpoint("help_subcommand", ["help"], "offline", 0, "TradeXV2 CLI", 10),
    CliEndpoint("unknown_command", ["nope-not-a-cmd"], "offline", 1, "Unknown command", 10),
    CliEndpoint("analytics_missing_sub", ["analytics"], "offline", 1, "analytics", 10),
    CliEndpoint("analytics_unknown_sub", ["analytics", "bogus"], "offline", 1, None, 15),
    CliEndpoint("validate_no_args", ["validate"], "offline", 0, "validate", 10),
    CliEndpoint(
        "doctor_quick",
        ["doctor", "--quick"],
        "offline",
        0,
        None,
        30,
        capability_id="monitoring.api_health",
    ),
    CliEndpoint("journal_list", ["journal", "list"], "offline", 0, None, 15),
    CliEndpoint("journal_no_args", ["journal"], "offline", 0, "Trade Journal", 10),
    CliEndpoint("views_list", ["views", "list"], "offline", 0, None, 15),
    CliEndpoint("views_no_args", ["views"], "offline", 0, "View", 10),
    CliEndpoint("options_sync_dry", ["options-sync", "--dry-run"], "offline", 0, None, 30),
    CliEndpoint("options_sync_no_args", ["options-sync"], "offline", 0, None, 30),
    CliEndpoint("cache_status", ["cache", "status"], "offline", 0, None, 10),
    CliEndpoint("cache_stats", ["cache", "stats"], "offline", 0, None, 10),
    CliEndpoint("cache_no_args", ["cache"], "offline", 0, None, 10),
    CliEndpoint("risk_status", ["risk", "status"], "offline", 0, None, 10),
    CliEndpoint("risk_no_args", ["risk"], "offline", 0, "risk", 10),
    CliEndpoint("instruments_stats", ["instruments", "stats"], "offline", 0, None, 15),
    CliEndpoint("broker", ["broker"], "offline", 0, None, 15),
    CliEndpoint("broker_list", ["broker", "list"], "offline", 0, None, 15),
    CliEndpoint("load_test_no_args", ["load-test"], "offline", 0, "load-test", 10),
]


# ── live_readonly endpoints (require .env.local + valid Dhan token) ─
LIVE_READONLY_ENDPOINTS: list[CliEndpoint] = [
    CliEndpoint(
        "account", ["account"], "live_readonly", 0, None, 30, capability_id="portfolio.funds"
    ),
    CliEndpoint(
        "funds_alias", ["funds"], "live_readonly", 0, None, 30, capability_id="portfolio.funds"
    ),
    CliEndpoint(
        "holdings", ["holdings"], "live_readonly", 0, None, 30, capability_id="portfolio.holdings"
    ),
    CliEndpoint(
        "positions",
        ["positions"],
        "live_readonly",
        0,
        None,
        30,
        capability_id="portfolio.positions",
    ),
    CliEndpoint(
        "orders", ["orders"], "live_readonly", 0, None, 30, capability_id="orders.query_orderbook"
    ),
    CliEndpoint(
        "trades", ["trades"], "live_readonly", 0, None, 30, capability_id="orders.query_trades"
    ),
    CliEndpoint(
        "oms", ["oms"], "live_readonly", 0, None, 30, capability_id="orders.query_orderbook"
    ),
    CliEndpoint(
        "quote",
        ["quote", "RELIANCE"],
        "live_readonly",
        0,
        None,
        30,
        capability_id="market_data.quote",
    ),
    CliEndpoint(
        "depth",
        ["depth", "RELIANCE"],
        "live_readonly",
        0,
        None,
        30,
        capability_id="market_data.depth",
    ),
    CliEndpoint(
        "historical",
        ["historical", "RELIANCE", "--days", "5"],
        "live_readonly",
        0,
        None,
        30,
        capability_id="market_data.history",
    ),
    CliEndpoint(
        "history_alias",
        ["history", "RELIANCE", "--days", "5"],
        "live_readonly",
        0,
        None,
        30,
        capability_id="market_data.history",
    ),
    CliEndpoint(
        "option_chain",
        ["option-chain", "RELIANCE"],
        "live_readonly",
        0,
        None,
        45,
        capability_id="derivatives.option_chain",
    ),
    CliEndpoint(
        "futures",
        ["futures", "RELIANCE"],
        "live_readonly",
        0,
        None,
        30,
        capability_id="derivatives.future_chain",
    ),
    CliEndpoint(
        "search",
        ["search", "RELIANCE"],
        "live_readonly",
        0,
        None,
        30,
        capability_id="instruments.search",
    ),
    CliEndpoint(
        "instrument",
        ["instrument", "RELIANCE"],
        "live_readonly",
        0,
        None,
        30,
        capability_id="interface.api.symbols",
    ),
    CliEndpoint(
        "instrument_info_alias",
        ["instrument-info", "RELIANCE"],
        "live_readonly",
        0,
        None,
        30,
        capability_id="interface.api.symbols",
    ),
    CliEndpoint(
        "instruments_lookup",
        ["instruments", "lookup", "RELIANCE"],
        "live_readonly",
        0,
        None,
        30,
        capability_id="instruments.search",
    ),
    CliEndpoint(
        "validate_broker",
        ["validate", "broker"],
        "live_readonly",
        0,
        None,
        30,
        capability_id="market_data.quote",
    ),
    CliEndpoint(
        "validate_symbol",
        ["validate", "RELIANCE"],
        "live_readonly",
        0,
        None,
        30,
        capability_id="market_data.history",
    ),
    CliEndpoint(
        "validate_history_sym",
        ["validate-history", "RELIANCE"],
        "live_readonly",
        0,
        None,
        30,
        capability_id="market_data.history",
    ),
    CliEndpoint(
        "validate_option_chain_sym",
        ["validate-option-chain", "RELIANCE"],
        "live_readonly",
        0,
        None,
        30,
        capability_id="derivatives.option_chain",
    ),
    CliEndpoint(
        "news",
        ["news", "--limit", "5"],
        "live_readonly",
        0,
        None,
        30,
        capability_id="capability.news",
    ),
    CliEndpoint(
        "websocket_once",
        ["websocket", "--once"],
        "live_readonly",
        0,
        None,
        30,
        capability_id="streaming.websocket",
    ),
    CliEndpoint(
        "compare_quote",
        ["compare", "quote", "RELIANCE"],
        "live_readonly",
        0,
        None,
        30,
        capability_id="market_data.quote",
    ),
    CliEndpoint(
        "benchmark",
        ["benchmark"],
        "live_readonly",
        0,
        None,
        60,
        capability_id="market_data.history",
    ),
    CliEndpoint(
        "quality_report",
        ["quality-report"],
        "live_readonly",
        0,
        None,
        60,
        capability_id="interface.api.analytics",
    ),
    CliEndpoint(
        "dashboard", ["dashboard"], "live_readonly", 0, None, 60, capability_id="market_data.ltp"
    ),
    CliEndpoint(
        "doctor_full",
        ["doctor"],
        "live_readonly",
        0,
        None,
        60,
        capability_id="monitoring.api_health",
    ),
    # Analytics subcommands with RELIANCE-based data
    CliEndpoint(
        "analytics_breadth",
        ["analytics", "breadth"],
        "live_readonly",
        0,
        None,
        60,
        capability_id="interface.api.analytics",
    ),
    CliEndpoint(
        "analytics_replay",
        ["analytics", "replay", "--symbol", "RELIANCE"],
        "live_readonly",
        0,
        None,
        60,
        capability_id="interface.api.replay",
    ),
    # Load tests (offline category but real broker) — keep short
    CliEndpoint(
        "load_test_historical",
        ["load-test", "historical"],
        "live_readonly",
        0,
        None,
        30,
        capability_id="market_data.history",
        no_subprocess=True,
    ),
    CliEndpoint(
        "load_test_quotes",
        ["load-test", "quotes"],
        "live_readonly",
        0,
        None,
        30,
        capability_id="market_data.quote",
        no_subprocess=True,
    ),
]


# ── sandbox endpoints (place/cancel — opt-in DHAN_INTEGRATION=1) ──────
SANDBOX_ENDPOINTS: list[CliEndpoint] = [
    CliEndpoint(
        "place_order_market",
        ["place-order", "RELIANCE", "BUY", "1", "--type", "MARKET"],
        "sandbox",
        0,
        None,
        30,
        capability_id="orders.place",
    ),
    CliEndpoint(
        "cancel_order_dummy",
        ["cancel-order", "TEST-NOT-EXIST"],
        "sandbox",
        1,
        None,
        30,
        capability_id="orders.cancel",
    ),
    CliEndpoint(
        "modify_order_dummy",
        ["modify-order", "TEST-NOT-EXIST"],
        "sandbox",
        1,
        None,
        30,
        capability_id="orders.modify",
    ),
]


# ── destructive (excluded from automated matrix, listed for docs) ─────
DESTRUCTIVE_ENDPOINTS: list[CliEndpoint] = [
    CliEndpoint("cache_clear", ["cache", "clear", "--confirm"], "destructive", 0, None, 30),
    CliEndpoint("cache_refresh", ["cache", "refresh"], "destructive", 0, None, 120),
    CliEndpoint("risk_reset_pnl", ["risk", "reset-pnl", "--confirm"], "destructive", 0, None, 15),
    CliEndpoint("risk_kill_switch_on", ["risk", "kill-switch", "on"], "destructive", 0, None, 15),
    CliEndpoint(
        "place_orders_batch",
        ["place-orders", "--file", "/tmp/orders.csv"],
        "destructive",
        0,
        None,
        30,
    ),
    CliEndpoint(
        "bracket_order",
        ["bracket-order", "RELIANCE", "BUY", "1", "--target", "2500", "--stop-loss", "2400"],
        "destructive",
        0,
        None,
        30,
    ),
    CliEndpoint(
        "oco_order",
        ["oco-order", "RELIANCE", "BUY", "1", "--order1-price", "2500", "--order2-price", "2400"],
        "destructive",
        0,
        None,
        30,
    ),
    CliEndpoint(
        "basket_order", ["basket-order", "--file", "/tmp/basket.csv"], "destructive", 0, None, 30
    ),
    CliEndpoint("analytics_paper", ["analytics", "paper"], "destructive", 0, None, 60),
    CliEndpoint("analytics_backtest", ["analytics", "backtest"], "destructive", 0, None, 120),
    CliEndpoint("analytics_optimize", ["analytics", "optimize"], "destructive", 0, None, 120),
    CliEndpoint(
        "analytics_datalake_backtest",
        ["analytics", "datalake-backtest"],
        "destructive",
        0,
        None,
        120,
    ),
    CliEndpoint("stream", ["stream", "RELIANCE"], "destructive", 0, None, 30),
    CliEndpoint("events", ["events"], "destructive", 0, None, 30),
]


ALL_ENDPOINTS: list[CliEndpoint] = (
    OFFLINE_ENDPOINTS + LIVE_READONLY_ENDPOINTS + SANDBOX_ENDPOINTS + DESTRUCTIVE_ENDPOINTS
)


# Top-level command names actually registered in cli/main.py.
# Updated from registry import in test_command_registry.py; this
# constant is the canonical list for T0 contract tests.
TOP_LEVEL_COMMANDS: list[str] = [
    "broker",
    "dashboard",
    "validate",
    "validate-history",
    "validate-option-chain",
    "options-sync",
    "benchmark",
    "compare",
    "quality-report",
    "instrument-info",
    "account",
    "funds",
    "holdings",
    "positions",
    "orders",
    "trades",
    "oms",
    "quote",
    "depth",
    "option-chain",
    "futures",
    "historical",
    "history",
    "stream",
    "websocket",
    "journal",
    "events",
    "search",
    "instrument",
    "instruments",
    "doctor",
    "load-test",
    "news",
    "analytics",
    "views",
    "place-order",
    "cancel-order",
    "modify-order",
    "place-orders",
    "bracket-order",
    "oco-order",
    "basket-order",
    "risk",
    "cache",
]


__all__ = [
    "ALL_ENDPOINTS",
    "DESTRUCTIVE_ENDPOINTS",
    "LIVE_READONLY_ENDPOINTS",
    "OFFLINE_ENDPOINTS",
    "SANDBOX_ENDPOINTS",
    "TOP_LEVEL_COMMANDS",
    "CliEndpoint",
    "Tier",
]
