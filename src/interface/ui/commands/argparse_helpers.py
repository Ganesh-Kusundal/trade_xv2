"""Shared CLI argument parsing helpers.

Eliminates the repeated ``--flag`` + ``idx + 1`` pattern and the
"missing symbol / no gateway" preamble that appeared in every
market handler and order command.
"""

from __future__ import annotations

from typing import Any

from rich.console import Console

from interface.ui.commands.registry import CommandResult
from interface.ui.services.broker_service import BrokerService


def parse_flag(args: list[str], flag: str) -> str | None:
    """Extract the value following ``flag`` in *args*, or ``None``.

    >>> parse_flag(["--price", "150.00"], "--price")
    '150.00'
    >>> parse_flag(["--price"], "--price") is None
    True
    >>> parse_flag(["--type", "LIMIT"], "--exchange") is None
    True
    """
    if flag not in args:
        return None
    idx = args.index(flag)
    if idx + 1 < len(args):
        return args[idx + 1]
    return None


def require_symbol(
    args: list[str],
    broker_service: BrokerService,
    console: Console,
    *,
    usage: str,
) -> tuple[str, Any] | CommandResult:
    """Validate that *args* has a symbol and a live gateway.

    Returns ``(symbol, gateway)`` on success, or a ``CommandResult``
    error that the caller should return immediately.
    """
    if not args:
        console.print(f"[yellow]Usage: {usage}[/yellow]")
        return CommandResult(success=False, error="Missing symbol")
    symbol = args[0]
    gw = broker_service.active_broker
    if gw is None:
        return CommandResult(
            success=False,
            error="No broker gateway available. Check credentials.",
        )
    return symbol, gw
