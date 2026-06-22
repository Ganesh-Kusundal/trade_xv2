"""CLI commands for risk management controls.

Exposes RiskManager controls including kill switch, position limits, and daily PnL.

Commands:
    tradex risk status        # View risk manager state
    tradex risk kill-switch on|off
    tradex risk limits        # View position limits
    tradex risk pnl           # View daily PnL
    tradex risk reset-pnl     # Reset daily PnL
"""

from __future__ import annotations

import logging

from rich.console import Console
from rich.table import Table

from cli.commands.registry import CommandResult
from cli.services.broker_service import BrokerService

logger = logging.getLogger(__name__)


def show_risk_status(args: list[str], broker_service: BrokerService, console: Console) -> CommandResult:
    """Display current risk manager state."""
    trading_ctx = broker_service.trading_context
    if trading_ctx is None:
        console.print("[red]TradingContext not initialized[/red]")
        return CommandResult(success=False, error="TradingContext not initialized")

    risk_mgr = trading_ctx.order_manager.risk_manager
    if risk_mgr is None:
        console.print("[yellow]RiskManager not configured[/yellow]")
        return CommandResult(success=False, error="RiskManager not configured")

    try:
        # Get risk state
        capital = risk_mgr._capital_provider.get_available_balance()
        daily_pnl = risk_mgr.daily_pnl
        kill_switch = risk_mgr.kill_switch

        # Display with Rich
        table = Table(title="⚠️ Risk Manager Status", header_style="bold yellow")
        table.add_column("Parameter", style="bold white")
        table.add_column("Value", justify="right")
        table.add_column("Status")

        table.add_row("Available Capital", f"₹{capital:,.2f}", "[green]OK[/green]")

        pnl_style = "green" if daily_pnl >= 0 else "red"
        table.add_row(
            "Daily PnL",
            f"₹{daily_pnl:,.2f}",
            f"[{pnl_style}]{'+' if daily_pnl >= 0 else ''}{daily_pnl:.2f}[/]",
        )

        ks_style = "red" if kill_switch else "green"
        table.add_row(
            "Kill Switch",
            "ACTIVE" if kill_switch else "inactive",
            f"[{ks_style}]{'🔴' if kill_switch else '🟢'}[/]",
        )

        console.print(table)

        return CommandResult(
            success=True,
            data={
                "capital": str(capital),
                "daily_pnl": str(daily_pnl),
                "kill_switch": kill_switch,
            },
        )
    except Exception as exc:
        console.print(f"[red]Failed to get risk status: {exc}[/red]")
        return CommandResult(success=False, error=str(exc))


def toggle_kill_switch(args: list[str], broker_service: BrokerService, console: Console) -> CommandResult:
    """Toggle kill switch on/off."""
    if not args:
        console.print("[yellow]Usage: tradex risk kill-switch on|off[/yellow]")
        return CommandResult(success=False, error="Missing on/off argument")

    action = args[0].lower()
    if action not in ("on", "off"):
        console.print("[yellow]Invalid action. Use 'on' or 'off'[/yellow]")
        return CommandResult(success=False, error="Invalid action. Use 'on' or 'off'")

    trading_ctx = broker_service.trading_context
    if trading_ctx is None:
        console.print("[red]TradingContext not initialized[/red]")
        return CommandResult(success=False, error="TradingContext not initialized")

    risk_mgr = trading_ctx.order_manager.risk_manager
    if risk_mgr is None:
        console.print("[yellow]RiskManager not configured[/yellow]")
        return CommandResult(success=False, error="RiskManager not configured")

    try:
        if action == "on":
            risk_mgr.set_kill_switch(True)
            console.print("[red]🔴 Kill switch ACTIVATED - All orders blocked[/red]")
            return CommandResult(success=True, data={"kill_switch": True})
        else:  # off
            risk_mgr.set_kill_switch(False)
            console.print("[green]🟢 Kill switch DEACTIVATED - Orders allowed[/green]")
            return CommandResult(success=True, data={"kill_switch": False})
    except Exception as exc:
        console.print(f"[red]Failed to toggle kill switch: {exc}[/red]")
        return CommandResult(success=False, error=str(exc))


def show_risk_limits(args: list[str], broker_service: BrokerService, console: Console) -> CommandResult:
    """Display position limits."""
    trading_ctx = broker_service.trading_context
    if trading_ctx is None:
        console.print("[red]TradingContext not initialized[/red]")
        return CommandResult(success=False, error="TradingContext not initialized")

    risk_mgr = trading_ctx.order_manager.risk_manager
    if risk_mgr is None:
        console.print("[yellow]RiskManager not configured[/yellow]")
        return CommandResult(success=False, error="RiskManager not configured")

    try:
        # Get config
        config = risk_mgr._config

        table = Table(title="📊 Risk Limits", header_style="bold cyan")
        table.add_column("Limit", style="bold white")
        table.add_column("Value", justify="right")
        table.add_column("Description")

        table.add_row(
            "Max Daily Loss",
            f"{config.max_daily_loss_pct:.1f}%",
            "Of available capital",
        )
        table.add_row(
            "Max Position Size",
            f"{config.max_position_pct:.1f}%",
            "Per symbol",
        )
        table.add_row(
            "Max Gross Exposure",
            f"{config.max_gross_exposure_pct:.1f}%",
            "Total portfolio",
        )

        console.print(table)

        return CommandResult(
            success=True,
            data={
                "max_daily_loss_pct": str(config.max_daily_loss_pct),
                "max_position_pct": str(config.max_position_pct),
                "max_gross_exposure_pct": str(config.max_gross_exposure_pct),
            },
        )
    except Exception as exc:
        console.print(f"[red]Failed to get risk limits: {exc}[/red]")
        return CommandResult(success=False, error=str(exc))


def show_daily_pnl(args: list[str], broker_service: BrokerService, console: Console) -> CommandResult:
    """Display daily PnL."""
    trading_ctx = broker_service.trading_context
    if trading_ctx is None:
        console.print("[red]TradingContext not initialized[/red]")
        return CommandResult(success=False, error="TradingContext not initialized")

    risk_mgr = trading_ctx.order_manager.risk_manager
    if risk_mgr is None:
        console.print("[yellow]RiskManager not configured[/yellow]")
        return CommandResult(success=False, error="RiskManager not configured")

    try:
        daily_pnl = risk_mgr.daily_pnl

        if daily_pnl >= 0:
            console.print(f"\n[bold green]Daily PnL: +₹{daily_pnl:,.2f}[/bold green]")
        else:
            console.print(f"\n[bold red]Daily PnL: ₹{daily_pnl:,.2f}[/bold red]")

        return CommandResult(success=True, data={"daily_pnl": str(daily_pnl)})
    except Exception as exc:
        console.print(f"[red]Failed to get daily PnL: {exc}[/red]")
        return CommandResult(success=False, error=str(exc))


def reset_daily_pnl(args: list[str], broker_service: BrokerService, console: Console) -> CommandResult:
    """Reset daily PnL."""
    if "--confirm" not in args:
        console.print("[yellow]This will reset daily PnL counter.[/yellow]")
        console.print("[yellow]Usage: tradex risk reset-pnl --confirm[/yellow]")
        return CommandResult(success=False, error="Confirmation required: use --confirm")

    trading_ctx = broker_service.trading_context
    if trading_ctx is None:
        console.print("[red]TradingContext not initialized[/red]")
        return CommandResult(success=False, error="TradingContext not initialized")

    risk_mgr = trading_ctx.order_manager.risk_manager
    if risk_mgr is None:
        console.print("[yellow]RiskManager not configured[/yellow]")
        return CommandResult(success=False, error="RiskManager not configured")

    try:
        risk_mgr.reset_daily_pnl()
        console.print("[green]✅ Daily PnL reset to ₹0.00[/green]")
        return CommandResult(success=True, data={"daily_pnl": "0.00"})
    except Exception as exc:
        console.print(f"[red]Failed to reset daily PnL: {exc}[/red]")
        return CommandResult(success=False, error=str(exc))


def run(args: list[str], broker_service: BrokerService, console: Console) -> CommandResult:
    """Entry point for risk commands."""
    if not args:
        console.print("[yellow]Usage: tradex risk [status|kill-switch|limits|pnl|reset-pnl][/yellow]")
        return CommandResult(success=False, error="Missing subcommand")

    subcmd = args[0].lower()

    if subcmd == "status":
        return show_risk_status(args[1:], broker_service, console)
    elif subcmd == "kill-switch":
        return toggle_kill_switch(args[1:], broker_service, console)
    elif subcmd == "limits":
        return show_risk_limits(args[1:], broker_service, console)
    elif subcmd == "pnl":
        return show_daily_pnl(args[1:], broker_service, console)
    elif subcmd == "reset-pnl":
        return reset_daily_pnl(args[1:], broker_service, console)
    else:
        console.print(f"[red]Unknown risk subcommand: {subcmd}[/red]")
        return CommandResult(success=False, error=f"Unknown subcommand: {subcmd}")
