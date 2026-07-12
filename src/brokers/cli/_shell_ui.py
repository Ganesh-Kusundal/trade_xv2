"""Rich UI helpers for the broker interactive shell."""

from __future__ import annotations

from typing import Any

from rich.panel import Panel

from brokers.cli._render import console


def _orders_label(enabled: Any) -> str:
    if enabled is True:
        return "[green]on[/green]"
    if enabled is False:
        return "[red]off[/red]"
    return "[dim]?[/dim]"


def render_header(
    session_info: dict[str, Any],
    broker_id: str,
    *,
    out: Any | None = None,
) -> None:
    """Render connected status panel."""
    target = out or console
    mode = session_info.get("mode") or "?"
    orders = session_info.get("orders_enabled")
    header = (
        f"[bold]Trading OS Broker Shell[/bold]\n"
        f"broker=[cyan]{broker_id}[/cyan]  "
        f"mode=[yellow]{mode}[/yellow]  "
        f"orders={_orders_label(orders)}"
    )
    if not session_info.get("connected", True):
        header += "\n[red]not connected[/red]"
        remediation = session_info.get("remediation", "")
        if remediation:
            header += f" — {remediation}"
        elif session_info.get("error"):
            err = str(session_info["error"])
            if len(err) > 120:
                err = err[:117] + "..."
            header += f" — {err}"
    target.print(Panel(header, border_style="cyan"))
