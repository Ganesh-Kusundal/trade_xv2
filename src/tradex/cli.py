"""Unified ``tradex`` command — single facade over the OS CLIs.

This module is a thin dispatcher only. It does not reimplement any broker
or UI logic; it wires together the existing entry points:

* ``interface.ui.main:main`` — the rich/Textual terminal entrypoint.
* ``config`` (below) — CLI-only preferences (broker.default, output.format),
  backed by ``tradex.preferences.PreferencesStore``. Not AppConfig —
  see that module's docstring for what this does and does not manage.

Install the console script via ``[project.scripts] tradex = "tradex.cli:tradex"``.
"""

from __future__ import annotations

import importlib
import json
import sys

import click

from tradex.preferences import PreferencesStore

# Forward flags like ``--broker dhan`` into interface.ui.main (Click would
# otherwise reject unknown options on the wrapper command itself).
_PASSTHROUGH = {"ignore_unknown_options": True}


@click.group()
@click.version_option(package_name="tradexv2")
def tradex() -> None:
    """TradeXV2 unified command — UI + analytics surface."""


def _dispatch_ui(argv: list[str]) -> None:
    """Re-invoke ``interface.ui.main`` with a translated argv.

    Reuses its existing broker/gateway bootstrap and the ``analytics``
    flat dispatcher rather than re-wiring a second copy of that plumbing.
    """
    main = importlib.import_module("interface.ui.main").main
    sys.argv = [sys.argv[0], *argv]
    main()


@tradex.command(context_settings=_PASSTHROUGH)
@click.argument("args", nargs=-1, type=click.UNPROCESSED)
def ui(args: tuple[str, ...]) -> None:
    """Launch the TradeXV2 rich/Textual terminal (interface.ui.main).

    Examples::

        tradex ui quote RELIANCE --broker dhan
        tradex ui option-chain BANKNIFTY --broker dhan
    """
    _dispatch_ui(list(args))


# ── Analytics-first top-level groups ────────────────────────────────────────
# Each command below is a thin argv-translator into the existing
# ``analytics`` flat dispatcher (``interface.ui.commands.analytics.run``),
# reusing its broker_service/gateway wiring rather than duplicating it. Only
# subcommands with a real backing engine are wired — see
# context/progress-tracker.md's "Analytics-first CLI pivot" entry for what's
# intentionally left out (no backing engine yet: pattern detect, market
# advance-decline/heatmap/leaders/laggards, volume spikes/unusual/delivery/
# delta/dry-up, scanner opening-range/custom).


@tradex.group()
def scanner() -> None:
    """Market scanners (breakout, volume, momentum, relative strength)."""


@scanner.command("breakout", context_settings=_PASSTHROUGH)
@click.argument("args", nargs=-1, type=click.UNPROCESSED)
def scanner_breakout(args: tuple[str, ...]) -> None:
    """Scan the universe for breakout candidates."""
    _dispatch_ui(["analytics", "scan-breakout", *args])


@scanner.command("volume", context_settings=_PASSTHROUGH)
@click.argument("args", nargs=-1, type=click.UNPROCESSED)
def scanner_volume(args: tuple[str, ...]) -> None:
    """Scan the universe for unusual-volume candidates."""
    _dispatch_ui(["analytics", "scan-volume", *args])


@scanner.command("momentum", context_settings=_PASSTHROUGH)
@click.argument("args", nargs=-1, type=click.UNPROCESSED)
def scanner_momentum(args: tuple[str, ...]) -> None:
    """Scan the universe for momentum candidates."""
    _dispatch_ui(["analytics", "scan-momentum", *args])


@scanner.command("rs", context_settings=_PASSTHROUGH)
@click.argument("args", nargs=-1, type=click.UNPROCESSED)
def scanner_rs(args: tuple[str, ...]) -> None:
    """Scan the universe for relative-strength candidates."""
    _dispatch_ui(["analytics", "scan-rs", *args])


@tradex.group()
def market() -> None:
    """Market breadth and sector analytics."""


@market.command("breadth", context_settings=_PASSTHROUGH)
@click.argument("args", nargs=-1, type=click.UNPROCESSED)
def market_breadth(args: tuple[str, ...]) -> None:
    """Advance/decline market breadth."""
    _dispatch_ui(["analytics", "breadth", *args])


@market.command("sector", context_settings=_PASSTHROUGH)
@click.argument("args", nargs=-1, type=click.UNPROCESSED)
def market_sector(args: tuple[str, ...]) -> None:
    """Sector-level analytics."""
    _dispatch_ui(["analytics", "sector", *args])


@market.command("sector-rotation", context_settings=_PASSTHROUGH)
@click.argument("args", nargs=-1, type=click.UNPROCESSED)
def market_sector_rotation(args: tuple[str, ...]) -> None:
    """Sector rotation analytics."""
    _dispatch_ui(["analytics", "sector-rotation", *args])


@market.command("sector-strength", context_settings=_PASSTHROUGH)
@click.argument("args", nargs=-1, type=click.UNPROCESSED)
def market_sector_strength(args: tuple[str, ...]) -> None:
    """Sector strength ranking."""
    _dispatch_ui(["analytics", "sector-strength", *args])


@market.command("sector-volume", context_settings=_PASSTHROUGH)
@click.argument("args", nargs=-1, type=click.UNPROCESSED)
def market_sector_volume(args: tuple[str, ...]) -> None:
    """Sector volume analytics."""
    _dispatch_ui(["analytics", "sector-volume", *args])


@tradex.group()
def indicator() -> None:
    """Technical indicators."""


@indicator.command("halftrend", context_settings=_PASSTHROUGH)
@click.argument("args", nargs=-1, type=click.UNPROCESSED)
def indicator_halftrend(args: tuple[str, ...]) -> None:
    """Halftrend indicator for a symbol."""
    _dispatch_ui(["analytics", "halftrend", *args])


@indicator.command("halftrend-scan", context_settings=_PASSTHROUGH)
@click.argument("args", nargs=-1, type=click.UNPROCESSED)
def indicator_halftrend_scan(args: tuple[str, ...]) -> None:
    """Scan the universe for halftrend signals."""
    _dispatch_ui(["analytics", "halftrend-scan", *args])


@tradex.group()
def strategy() -> None:
    """Registered trading strategies."""


@strategy.command("list", context_settings=_PASSTHROUGH)
@click.argument("args", nargs=-1, type=click.UNPROCESSED)
def strategy_list(args: tuple[str, ...]) -> None:
    """List registered strategies."""
    _dispatch_ui(["analytics", "strategies", *args])


@tradex.group()
def backtest() -> None:
    """Backtest, paper, and replay simulation (zero-parity OMS kernel)."""


@backtest.command("run", context_settings=_PASSTHROUGH)
@click.argument("args", nargs=-1, type=click.UNPROCESSED)
def backtest_run(args: tuple[str, ...]) -> None:
    """Run a backtest."""
    _dispatch_ui(["analytics", "backtest", *args])


@backtest.command("paper", context_settings=_PASSTHROUGH)
@click.argument("args", nargs=-1, type=click.UNPROCESSED)
def backtest_paper(args: tuple[str, ...]) -> None:
    """Run paper-trading simulation."""
    _dispatch_ui(["analytics", "paper", *args])


@backtest.command("replay", context_settings=_PASSTHROUGH)
@click.argument("args", nargs=-1, type=click.UNPROCESSED)
def backtest_replay(args: tuple[str, ...]) -> None:
    """Replay historical data through the OMS kernel."""
    _dispatch_ui(["analytics", "replay", *args])


@backtest.command("optimize", context_settings=_PASSTHROUGH)
@click.argument("args", nargs=-1, type=click.UNPROCESSED)
def backtest_optimize(args: tuple[str, ...]) -> None:
    """Grid-search strategy parameters."""
    _dispatch_ui(["analytics", "optimize", *args])


@backtest.command("walkforward", context_settings=_PASSTHROUGH)
@click.argument("args", nargs=-1, type=click.UNPROCESSED)
def backtest_walkforward(args: tuple[str, ...]) -> None:
    """Walk-forward validation."""
    _dispatch_ui(["analytics", "walkforward", *args])


@tradex.group()
def support() -> None:
    """Support/resistance levels (read-only datalake query)."""


@support.command("levels")
@click.argument("symbol")
@click.option("--days", default=60, type=int, help="Lookback window in days.")
@click.option("--top-n", "top_n", default=5, type=int, help="Number of levels per side.")
@click.pass_context
def support_levels(ctx: click.Context, symbol: str, days: int, top_n: int) -> None:
    """Support/resistance levels for SYMBOL."""
    from dataclasses import asdict

    from datalake.analytics.support_resistance import SupportResistance

    levels = SupportResistance().get_levels(symbol, days=days, top_n=top_n)
    data = {side: [asdict(lvl) for lvl in rows] for side, rows in levels.items()}
    click.echo(json.dumps(data, indent=2, default=str))


@support.command("nearest")
@click.argument("symbol")
@click.option("--price", type=float, required=True, help="Current price to compare against.")
@click.option("--days", default=60, type=int, help="Lookback window in days.")
@click.pass_context
def support_nearest(ctx: click.Context, symbol: str, price: float, days: int) -> None:
    """Nearest support/resistance to --price for SYMBOL."""
    from dataclasses import asdict

    from datalake.analytics.support_resistance import SupportResistance

    result = dict(SupportResistance().get_nearest_levels(symbol, price, days=days))
    for key in ("nearest_support", "nearest_resistance"):
        if result.get(key) is not None:
            result[key] = asdict(result[key])
    click.echo(json.dumps(result, indent=2, default=str))


# ``version`` is exposed automatically via ``--version`` on the group; this
# explicit command keeps it discoverable in ``tradex --help``.


@tradex.command(name="version")
def _version() -> None:
    """Print the installed TradeXV2 version."""
    from importlib.metadata import version

    try:
        click.echo(version("tradexv2"))
    except Exception:  # pragma: no cover - package metadata edge cases
        click.echo("tradexv2 (version metadata unavailable)")


@tradex.group()
@click.pass_context
def config(ctx: click.Context) -> None:
    """Manage tradex CLI preferences (broker.default, output.format)."""
    ctx.ensure_object(dict)
    ctx.obj.setdefault("prefs_store", PreferencesStore())


@config.command("list")
@click.pass_context
def config_list(ctx: click.Context) -> None:
    """Show all CLI preferences."""
    store: PreferencesStore = ctx.obj["prefs_store"]
    for key, value in store.load().items():
        click.echo(f"{key}={value}")


@config.command("get")
@click.argument("key")
@click.pass_context
def config_get(ctx: click.Context, key: str) -> None:
    """Print the value of KEY (e.g. broker.default)."""
    store: PreferencesStore = ctx.obj["prefs_store"]
    try:
        click.echo(store.get(key))
    except KeyError as exc:
        raise click.ClickException(str(exc)) from exc


@config.command("set")
@click.argument("key")
@click.argument("value")
@click.pass_context
def config_set(ctx: click.Context, key: str, value: str) -> None:
    """Set KEY to VALUE."""
    store: PreferencesStore = ctx.obj["prefs_store"]
    try:
        prefs = store.set(key, value)
    except KeyError as exc:
        raise click.ClickException(str(exc)) from exc
    click.echo(f"{key}={prefs.get(key)}")


@config.command("edit")
@click.pass_context
def config_edit(ctx: click.Context) -> None:
    """Open the preferences file in $EDITOR."""
    store: PreferencesStore = ctx.obj["prefs_store"]
    if not store.path().exists():
        store.save(store.load())
    click.edit(filename=str(store.path()))


@config.command("reset")
@click.confirmation_option(prompt="Reset all CLI preferences to defaults?")
@click.pass_context
def config_reset(ctx: click.Context) -> None:
    """Reset preferences to defaults."""
    store: PreferencesStore = ctx.obj["prefs_store"]
    store.reset()
    click.echo("Preferences reset.")


if __name__ == "__main__":
    tradex()
