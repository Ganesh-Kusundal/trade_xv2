"""CLI command handler for account operations.

Account data is accessed through a domain provider. No broker gateway is referenced.
"""

from __future__ import annotations

import logging
from decimal import Decimal
from typing import Protocol, runtime_checkable

from rich.console import Console
from rich.table import Table

logger = logging.getLogger(__name__)


@runtime_checkable
class AccountProvider(Protocol):
    """Domain port for account data — implemented by broker adapters."""

    def get_balance(self) -> any: ...
    def get_positions(self) -> list: ...


# ── Module-level provider (set once at startup) ─────────────────────
_provider: AccountProvider | None = None


def set_account_provider(provider: AccountProvider) -> None:
    global _provider
    _provider = provider


def _get_provider() -> AccountProvider:
    if _provider is None:
        raise RuntimeError("AccountProvider not wired — call set_account_provider() at startup")
    return _provider


def show_account(broker_service=None, console: Console | None = None) -> None:
    """Print active account limits and margin information."""
    provider = _get_provider()
    try:
        balance = provider.get_balance()
        positions = provider.get_positions()

        realized = sum(pos.realized_pnl for pos in positions)
        unrealized = sum(pos.unrealized_pnl for pos in positions)
        total_pnl = realized + unrealized

        table = Table(title="Account Summary", header_style="bold magenta")
        table.add_column("Metric", style="bold white")
        table.add_column("Value", justify="right")

        table.add_row("SOD Limit / Equity", f"Rs. {balance.sod_limit:,.2f}")
        table.add_row("Available Balance", f"Rs. {balance.available_balance:,.2f}")
        table.add_row("Utilized Amount", f"Rs. {balance.utilized_amount:,.2f}")
        table.add_row("Collateral Amount", f"Rs. {balance.collateral_amount:,.2f}")
        table.add_row("Withdrawable Balance", f"Rs. {balance.withdrawable_balance:,.2f}")

        def colorize_val(val: Decimal) -> str:
            if val > 0:
                return f"[green]Rs. {val:,.2f}[/green]"
            elif val < 0:
                return f"[red]Rs. {val:,.2f}[/red]"
            return f"[white]Rs. {val:,.2f}[/white]"

        table.add_row("Realized Day PnL", colorize_val(realized))
        table.add_row("Unrealized Day PnL", colorize_val(unrealized))
        table.add_row("Total Day PnL", colorize_val(total_pnl))

        console.print(table)
    except Exception as exc:
        console.print(f"[red]Error fetching account details: {exc}[/red]")


def run(args: list[str], broker_service=None, console: Console | None = None) -> None:
    """Entry point for account subcommand."""
    show_account(broker_service, console)
