"""CLI command handler for portfolio (holdings and positions) operations.

Portfolio data is accessed through a domain provider that returns
domain entities (Holding, Position). No broker gateway is referenced.
"""

from __future__ import annotations

import logging
from decimal import Decimal
from typing import TYPE_CHECKING, Protocol, runtime_checkable

from rich.console import Console
from rich.table import Table

from cli.commands.registry import CommandResult
from domain import Position

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)


@runtime_checkable
class PortfolioProvider(Protocol):
    """Domain port for portfolio data — implemented by broker adapters."""

    def get_holdings(self) -> list: ...
    def get_positions(self) -> list: ...
    def get_balance(self) -> Any: ...


# ── Module-level provider (set once at startup) ─────────────────────
_provider: PortfolioProvider | None = None


def set_portfolio_provider(provider: PortfolioProvider) -> None:
    global _provider
    _provider = provider


def _get_provider() -> PortfolioProvider:
    if _provider is None:
        raise RuntimeError("PortfolioProvider not wired — call set_portfolio_provider() at startup")
    return _provider


def show_holdings(broker_service=None, console: Console | None = None) -> CommandResult:
    """Print the holdings table and return CommandResult."""
    provider = _get_provider()
    try:
        holdings = provider.get_holdings()
        table = Table(title="Demat Holdings", header_style="bold green")
        table.add_column("Symbol", style="bold white")
        table.add_column("Qty", justify="right")
        table.add_column("Avg Price", justify="right")
        table.add_column("LTP", justify="right")
        table.add_column("PnL", justify="right")

        total_pnl = Decimal("0.00")
        holdings_data = []
        for h in holdings:
            pnl_val = h.pnl
            total_pnl += pnl_val
            pnl_style = "green" if pnl_val > 0 else ("red" if pnl_val < 0 else "white")
            table.add_row(
                h.symbol,
                str(h.quantity),
                f"{h.avg_price:,.2f}",
                f"{h.ltp:,.2f}",
                f"[{pnl_style}]Rs. {pnl_val:,.2f}[/{pnl_style}]",
            )
            holdings_data.append(
                {
                    "symbol": h.symbol,
                    "quantity": h.quantity,
                    "avg_price": str(h.avg_price),
                    "ltp": str(h.ltp),
                    "pnl": str(pnl_val),
                }
            )

        pnl_style = "green" if total_pnl > 0 else ("red" if total_pnl < 0 else "white")
        table.add_section()
        table.add_row("Total", "", "", "", f"[{pnl_style}]Rs. {total_pnl:,.2f}[/{pnl_style}]")

        console.print(table)
        return CommandResult(
            success=True,
            data={
                "holdings": holdings_data,
                "total_pnl": str(total_pnl),
                "count": len(holdings),
            },
        )
    except Exception as exc:
        logger.exception("holdings_fetch_failed")
        console.print(f"[red]Error fetching holdings: {exc}[/red]")
        return CommandResult(success=False, error=str(exc))


def show_positions(broker_service=None, console: Console | None = None) -> None:
    """Print positions categorized by side and product."""
    provider = _get_provider()
    try:
        positions = provider.get_positions()

        long_pos = [p for p in positions if p.quantity > 0]
        short_pos = [p for p in positions if p.quantity < 0]
        day_pos = [p for p in positions if p.product_type.value == "INTRADAY"]
        overnight_pos = [p for p in positions if p.product_type.value in ("CNC", "MARGIN", "MTF")]

        def render_position_table(title: str, pos_list: list[Position], style: str) -> None:
            table = Table(title=title, header_style=f"bold {style}")
            table.add_column("Symbol", style="bold white")
            table.add_column("Product", justify="center")
            table.add_column("Net Qty", justify="right")
            table.add_column("Avg Price", justify="right")
            table.add_column("LTP", justify="right")
            table.add_column("PnL", justify="right")

            total_pnl = Decimal("0.00")
            for p in pos_list:
                pnl_val = p.unrealized_pnl + p.realized_pnl
                total_pnl += pnl_val
                pnl_style = "green" if pnl_val > 0 else ("red" if pnl_val < 0 else "white")
                table.add_row(
                    p.symbol,
                    p.product_type.value,
                    str(p.quantity),
                    f"{p.avg_price:,.2f}",
                    f"{p.ltp:,.2f}",
                    f"[{pnl_style}]Rs. {pnl_val:,.2f}[/{pnl_style}]",
                )
            pnl_style = "green" if total_pnl > 0 else ("red" if total_pnl < 0 else "white")
            table.add_section()
            table.add_row(
                "Total PnL", "", "", "", "", f"[{pnl_style}]Rs. {total_pnl:,.2f}[/{pnl_style}]"
            )
            console.print(table)
            console.print()

        console.print("Positions Overview:")
        console.print()

        render_position_table("Long Positions", long_pos, "green")
        render_position_table("Short Positions", short_pos, "red")
        render_position_table("Day Positions (INTRADAY)", day_pos, "cyan")
        render_position_table("Overnight Positions (CNC/MARGIN)", overnight_pos, "magenta")

    except Exception as exc:
        console.print(f"[red]Error fetching positions: {exc}[/red]")


def run(args: list[str], broker_service=None, console: Console | None = None) -> None:
    """Entry point for portfolio subcommands."""
    pass
