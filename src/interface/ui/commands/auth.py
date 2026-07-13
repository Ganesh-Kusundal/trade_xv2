"""Auth management CLI: tradex auth status | refresh.

Light wrapper over the existing :class:`~interface.ui.services.broker_service.BrokerService`
auth state and :func:`bootstrap_gateway` token refresh.  Reuses the
auth bootstrap already performed by ``BrokerService``; never re-implements
token logic.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import TYPE_CHECKING, Any

from domain.enums import BrokerId
from rich.console import Console
from rich.table import Table

if TYPE_CHECKING:
    from interface.ui.services.broker_service import BrokerService

logger = logging.getLogger(__name__)

_ENV_PATH = Path(__file__).resolve().parent.parent.parent / ".env.local"


def run(args: list[str], broker_service: Any, console: Console) -> None:
    """Entry point: tradex auth <status|refresh>."""
    sub = (args[0].lower() if args else "status")
    if sub == "refresh":
        _refresh(broker_service, console)
    else:
        _status(broker_service, console)


def _status(broker_service: Any, console: Console) -> None:
    broker_service._ensure_initialized()
    gw = broker_service.active_broker
    name = broker_service.active_broker_name

    tbl = Table(title="Auth Status", header_style="bold cyan")
    tbl.add_column("Field", style="bold white")
    tbl.add_column("Value", justify="right")
    tbl.add_row("Active broker", name)
    tbl.add_row(
        "Live gateway",
        "[green]yes[/green]" if gw is not None else "[yellow]no[/yellow]",
    )
    tbl.add_row(
        "Live actionable",
        "[green]yes[/green]"
        if getattr(broker_service, "live_actionable", False)
        else "[yellow]no[/yellow]",
    )

    report = broker_service.readiness_report
    if report is not None and hasattr(report, "describe"):
        try:
            for k, v in report.describe().items():
                tbl.add_row(f"readiness.{k}", str(v))
        except Exception:
            pass

    load_err = broker_service.dhan_load_error
    if load_err:
        tbl.add_row("load error", f"[red]{load_err}[/red]")
    console.print(tbl)


def _refresh(broker_service: Any, console: Console) -> None:
    broker_service._ensure_initialized()
    console.print("[yellow]Re-running auth bootstrap…[/yellow]")
    try:
        from interface.ui.services.broker_registry import bootstrap_gateway

        result = bootstrap_gateway(
            BrokerId.DHAN, env_path=_ENV_PATH, load_instruments=True
        )
        if result.live_ready:
            console.print("[green]Token refreshed & live-ready.[/green]")
        else:
            console.print(
                f"[red]Refresh failed: {result.error or result.status.value}[/red]"
            )
    except Exception as exc:
        console.print(f"[red]Refresh failed: {exc}[/red]")
