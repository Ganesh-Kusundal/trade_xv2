"""CLI command handler for news."""

from __future__ import annotations

from typing import Any

from rich.console import Console
from rich.table import Table


def run(args: list[str], broker_service, console: Console) -> None:
    gateway = broker_service.active_broker
    if gateway is None:
        console.print("[red]No active broker. Connect first with: tradex broker connect[/red]")
        return

    if not hasattr(gateway, "news"):
        console.print("[red]Active broker does not support news.[/red]")
        console.print("[dim]News is currently available only with Upstox broker.[/dim]")
        return

    symbol = None
    from_date = None
    to_date = None
    limit = 20

    index = 0
    while index < len(args):
        arg = args[index]
        if arg in {"--symbol", "-s"} and index + 1 < len(args):
            symbol = args[index + 1].upper()
            index += 2
        elif arg in {"--from"} and index + 1 < len(args):
            from_date = args[index + 1]
            index += 2
        elif arg in {"--to"} and index + 1 < len(args):
            to_date = args[index + 1]
            index += 2
        elif arg == "--limit" and index + 1 < len(args):
            limit = int(args[index + 1])
            index += 2
        elif not arg.startswith("--"):
            symbol = arg.upper()
            index += 1
        else:
            index += 1

    try:
        news_provider = gateway.news
        filters: dict[str, Any] = {}
        if symbol:
            filters["symbol"] = symbol
        if from_date:
            filters["from_date"] = from_date
        if to_date:
            filters["to_date"] = to_date

        items = news_provider.get_news(**filters)

        if not items:
            console.print("[yellow]No news items found.[/yellow]")
            return

        table = Table(title=f"News{f': {symbol}' if symbol else ''}", header_style="bold cyan")
        table.add_column("#", style="dim", width=4)
        table.add_column("Headline", style="bold white", max_width=60)
        table.add_column("Source", style="cyan", width=12)
        table.add_column("Time", style="green", width=16)

        for i, item in enumerate(items[:limit], 1):
            headline = item.get("headline") or item.get("title") or item.get("summary", "N/A")
            source = item.get("source", "N/A")
            timestamp = item.get("timestamp") or item.get("published_at") or item.get("date", "N/A")
            if hasattr(timestamp, "strftime"):
                timestamp = timestamp.strftime("%Y-%m-%d %H:%M")
            table.add_row(str(i), str(headline)[:60], str(source), str(timestamp))

        console.print(table)
        console.print(f"[dim]{len(items)} total items, showing {min(limit, len(items))}[/dim]")

    except Exception as exc:
        console.print(f"[red]Error fetching news: {exc}[/red]")
