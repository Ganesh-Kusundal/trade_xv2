"""Monitoring / health and API product surfaces."""

from domain.capability_manifest.types import surface

MONITORING_SURFACES = (
    # ── Monitoring / health ──
    surface(
        "monitoring.api_health",
        cli=(("doctor", "src/interface/ui/commands/doctor/__init__.py"),),
        rest=(
            ("GET", "/api/v1/health", "src/interface/api/routers/health.py", "none"),
            ("GET", "/api/v1/health/readyz", "src/interface/api/routers/health.py", "none"),
            ("GET", "/api/v1/health/metrics", "src/interface/api/routers/health.py", "oms"),
            (
                "GET",
                "/api/v1/health/metrics/prometheus",
                "src/interface/api/routers/health.py",
                "none",
            ),
        ),
    ),
    surface(
        "monitoring.live_broker_health",
        cli=(("doctor", "src/interface/ui/commands/doctor/__init__.py"),),
        rest=(
            (
                "GET",
                "/api/v1/live/health",
                "src/interface/api/routers/live/health.py",
                "live_broker",
            ),
            (
                "GET",
                "/api/v1/live/readyz",
                "src/interface/api/routers/live/health.py",
                "live_broker",
            ),
            (
                "GET",
                "/api/v1/live/capabilities",
                "src/interface/api/routers/live/health.py",
                "live_broker",
            ),
        ),
    ),
)

API_PRODUCT_SURFACES = (
    # ── API product surfaces ──
    surface(
        "interface.api.scanner",
        cli=(("analytics scan", "src/interface/ui/commands/analytics_scanner.py"),),
        rest=(
            ("GET", "/api/v1/scanner/results", "src/interface/api/routers/scanner.py", "datalake"),
            (
                "GET",
                "/api/v1/scanner/top-candidates",
                "src/interface/api/routers/scanner.py",
                "datalake",
            ),
            (
                "GET",
                "/api/v1/scanner/snapshots",
                "src/interface/api/routers/scanner.py",
                "datalake",
            ),
            ("POST", "/api/v1/scanner/run", "src/interface/api/routers/scanner.py", "mixed"),
        ),
        tier="extended",
        severity_if_gap="P3",
    ),
    surface(
        "interface.api.backtest",
        cli=(("analytics backtest", "src/interface/ui/commands/analytics_backtest.py"),),
        rest=(
            ("POST", "/api/v1/backtest/run", "src/interface/api/routers/backtest.py", "datalake"),
            (
                "GET",
                "/api/v1/backtest/results/{backtest_id}",
                "src/interface/api/routers/backtest.py",
                "datalake",
            ),
            (
                "GET",
                "/api/v1/backtest/comparison/{run_id}",
                "src/interface/api/routers/backtest.py",
                "datalake",
            ),
        ),
        tier="extended",
        severity_if_gap="P3",
    ),
    surface(
        "interface.api.replay",
        cli=(("analytics replay", "src/interface/ui/commands/analytics_replay.py"),),
        rest=(
            ("GET", "/api/v1/replay/sessions", "src/interface/api/routers/replay.py", "datalake"),
            ("POST", "/api/v1/replay/sessions", "src/interface/api/routers/replay.py", "datalake"),
            (
                "GET",
                "/api/v1/replay/sessions/{session_id}",
                "src/interface/api/routers/replay.py",
                "datalake",
            ),
            (
                "POST",
                "/api/v1/replay/sessions/{session_id}/play",
                "src/interface/api/routers/replay.py",
                "datalake",
            ),
            (
                "POST",
                "/api/v1/replay/sessions/{session_id}/pause",
                "src/interface/api/routers/replay.py",
                "datalake",
            ),
            (
                "POST",
                "/api/v1/replay/sessions/{session_id}/stop",
                "src/interface/api/routers/replay.py",
                "datalake",
            ),
            (
                "POST",
                "/api/v1/replay/sessions/{session_id}/speed",
                "src/interface/api/routers/replay.py",
                "datalake",
            ),
            (
                "POST",
                "/api/v1/replay/sessions/{session_id}/seek",
                "src/interface/api/routers/replay.py",
                "datalake",
            ),
        ),
        tier="extended",
        severity_if_gap="P3",
    ),
    surface(
        "interface.api.analytics",
        cli=(("analytics breadth", "src/interface/ui/commands/analytics.py"),),
        rest=(
            (
                "GET",
                "/api/v1/analytics/market-breadth",
                "src/interface/api/routers/analytics.py",
                "datalake",
            ),
            (
                "GET",
                "/api/v1/analytics/indicators",
                "src/interface/api/routers/analytics.py",
                "datalake",
            ),
            (
                "GET",
                "/api/v1/scanner/snapshots",
                "src/interface/api/routers/scanner.py",
                "datalake",
            ),
            (
                "GET",
                "/api/v1/scanner/top-candidates",
                "src/interface/api/routers/scanner.py",
                "datalake",
            ),
            (
                "GET",
                "/api/v1/analytics/relative-strength",
                "src/interface/api/routers/analytics.py",
                "datalake",
            ),
        ),
        tier="extended",
        severity_if_gap="P3",
    ),
    surface(
        "interface.api.portfolio_summary",
        cli=(("oms", "src/interface/ui/commands/oms.py"),),
        rest=(
            ("GET", "/api/v1/portfolio/summary", "src/interface/api/routers/portfolio.py", "oms"),
            ("GET", "/api/v1/portfolio/pnl", "src/interface/api/routers/portfolio.py", "oms"),
        ),
        tier="extended",
    ),
    surface(
        "interface.api.symbols",
        cli=(
            ("instrument", "src/interface/ui/commands/instrument.py"),
            ("instrument", "src/brokers/cli/broker.py"),
        ),
        notes="MCP: broker_instrument_lookup; services: lookup_instrument",
        rest=(
            ("GET", "/api/v1/symbols/{symbol}", "src/interface/api/routers/symbols.py", "datalake"),
            (
                "GET",
                "/api/v1/symbols/universe/{name}",
                "src/interface/api/routers/symbols.py",
                "datalake",
            ),
        ),
    ),
    surface(
        "interface.api.strategy",
        cli=(("analytics strategies", "src/interface/ui/commands/analytics_strategies.py"),),
        rest=(
            (
                "GET",
                "/api/v1/strategy/signals",
                "src/interface/api/routers/strategy.py",
                "datalake",
            ),
            (
                "GET",
                "/api/v1/strategy/candidates",
                "src/interface/api/routers/strategy.py",
                "datalake",
            ),
            (
                "GET",
                "/api/v1/analytics/strategies",
                "src/interface/api/routers/analytics.py",
                "datalake",
            ),
            (
                "POST",
                "/api/v1/analytics/strategies/run",
                "src/interface/api/routers/analytics.py",
                "datalake",
            ),
        ),
        tier="extended",
        severity_if_gap="P3",
    ),
)
