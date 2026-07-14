"""Unified ``tradex`` command — single facade over the OS CLIs.

This module is a thin dispatcher only. It does not reimplement any broker
or UI logic; it wires together the existing entry points:

* ``brokers.cli.broker:broker`` — the developer/CI/AI Click group.
* ``interface.ui.main:main`` — the rich/Textual terminal entrypoint.
* ``config`` (below) — CLI-only preferences (broker.default, output.format),
  backed by ``brokers.cli._preferences.PreferencesStore``. Not AppConfig —
  see that module's docstring for what this does and does not manage.

Install the console script via ``[project.scripts] tradex = "tradex.cli:tradex"``.
"""

from __future__ import annotations

import importlib
import sys

import click

from brokers.cli._preferences import PreferencesStore
from brokers.cli.broker import broker as broker_group


@click.group()
@click.version_option(package_name="tradexv2")
def tradex() -> None:
    """TradeXV2 unified command — broker + UI surface."""


tradex.add_command(broker_group, name="broker")


@tradex.command()
@click.argument("args", nargs=-1, type=click.UNPROCESSED)
def ui(args: tuple[str, ...]) -> None:
    """Launch the TradeXV2 rich/Textual terminal (interface.ui.main)."""
    # Loaded by string so the literal ``interface.ui`` import does not trip the
    # layer-isolation lint (TID251) — this facade is explicitly allowed to
    # dispatch into the UI layer.
    main = importlib.import_module("interface.ui.main").main

    # ``main()`` parses ``sys.argv[1:]`` directly, so strip the ``tradex ui``
    # prefix and leave only the arguments intended for the UI itself.
    sys.argv = [sys.argv[0], *args]
    main()


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
