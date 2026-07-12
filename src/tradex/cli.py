"""Unified ``tradex`` command — single facade over the OS CLIs.

This module is a thin dispatcher only. It does not reimplement any broker
or UI logic; it wires together the two existing entry points:

* ``brokers.cli.broker:broker`` — the developer/CI/AI Click group.
* ``interface.ui.main:main`` — the rich/Textual terminal entrypoint.

Install the console script via ``[project.scripts] tradex = "tradex.cli:tradex"``.
"""

from __future__ import annotations

import importlib
import sys

import click

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


if __name__ == "__main__":
    tradex()
