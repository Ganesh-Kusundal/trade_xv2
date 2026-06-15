"""CLI commands for DuckDB analytics view management."""

from __future__ import annotations

from rich.console import Console
from rich.table import Table

from analytics.views.manager import ViewManager
from analytics.views.validator import PointInTimeValidator


def run_views(args: list[str], console: Console) -> None:
    """Manage DuckDB analytics views."""
    if not args:
        _print_help(console)
        return

    command = args[0].lower()

    if command == "create":
        _create_views(console)
    elif command == "drop":
        _drop_views(console)
    elif command == "refresh":
        _refresh_views(console)
    elif command == "list":
        _list_views(console)
    elif command == "benchmark":
        _benchmark_views(args[1:], console)
    elif command == "validate":
        _validate_views(console)
    elif command == "count":
        _count_views(console)
    else:
        console.print(f"[yellow]Unknown command: {command}[/yellow]")
        _print_help(console)


def _print_help(console: Console) -> None:
    """Print help."""
    console.print("[bold]DuckDB Analytics View Management[/bold]")
    console.print("[dim]Commands:[/dim]")
    console.print("  create     — Create all analytics views")
    console.print("  drop       — Drop all analytics views")
    console.print("  refresh    — Drop + recreate all views")
    console.print("  list       — List all existing views")
    console.print("  count      — Count total views")
    console.print("  benchmark  — Benchmark view query performance")
    console.print("  validate   — Validate point-in-time correctness")


def _create_views(console: Console) -> None:
    """Create all analytics views."""
    vm = ViewManager()
    try:
        console.print("[dim]Creating analytics views...[/dim]")
        timings = vm.create_all()

        table = Table(title="View Creation Timings", header_style="bold green")
        table.add_column("Layer", style="bold")
        table.add_column("Time (ms)", justify="right")
        table.add_column("Status")

        for layer, elapsed in timings.items():
            status = "[green]OK[/green]" if elapsed >= 0 else "[red]FAILED[/red]"
            table.add_row(layer, f"{elapsed * 1000:.0f}", status)

        console.print(table)
        console.print(f"[bold green]Total views created: {vm.view_count()}[/bold green]")
    finally:
        vm.close()


def _drop_views(console: Console) -> None:
    """Drop all analytics views."""
    vm = ViewManager()
    try:
        count_before = vm.view_count()
        vm.drop_all()
        console.print(f"[green]Dropped {count_before} views.[/green]")
    finally:
        vm.close()


def _refresh_views(console: Console) -> None:
    """Refresh all views."""
    vm = ViewManager()
    try:
        console.print("[dim]Refreshing all views...[/dim]")
        timings = vm.refresh()
        console.print(f"[bold green]Refreshed {vm.view_count()} views.[/bold green]")
    finally:
        vm.close()


def _list_views(console: Console) -> None:
    """List all views."""
    vm = ViewManager(read_only=True)
    try:
        views = vm.list_views()
        if not views:
            console.print("[dim]No views found.[/dim]")
            return

        table = Table(title=f"DuckDB Views ({len(views)})", header_style="bold cyan")
        table.add_column("View Name", style="bold")
        table.add_column("Columns", justify="right")

        for v in views:
            try:
                cols = vm.view_columns(v["name"])
                table.add_row(v["name"], str(len(cols)))
            except Exception:
                table.add_row(v["name"], "N/A")

        console.print(table)
    finally:
        vm.close()


def _count_views(console: Console) -> None:
    """Count views."""
    vm = ViewManager(read_only=True)
    try:
        count = vm.view_count()
        console.print(f"[bold]Total views: {count}[/bold]")
    finally:
        vm.close()


def _benchmark_views(args: list[str], console: Console) -> None:
    """Benchmark view queries."""
    vm = ViewManager(read_only=True)
    try:
        iterations = 5
        if args and args[0] == "--iterations" and len(args) > 1:
            iterations = int(args[1])

        console.print(f"[dim]Benchmarking with {iterations} iterations...[/dim]")
        results = vm.benchmark_all()

        if not results:
            console.print("[dim]No views to benchmark.[/dim]")
            return

        table = Table(title="Query Performance Benchmark", header_style="bold magenta")
        table.add_column("View", style="bold")
        table.add_column("Avg (ms)", justify="right", style="green")
        table.add_column("Min (ms)", justify="right")
        table.add_column("Max (ms)", justify="right")

        for r in results:
            table.add_row(
                r.get("view", "unknown"),
                f"{r['avg_ms']:.1f}",
                f"{r['min_ms']:.1f}",
                f"{r['max_ms']:.1f}",
            )

        console.print(table)
    finally:
        vm.close()


def _validate_views(console: Console) -> None:
    """Validate point-in-time correctness."""
    vm = ViewManager(read_only=True)
    try:
        validator = PointInTimeValidator(vm.conn)
        reports = validator.validate_all()
        summary = validator.generate_summary(reports)

        table = Table(title="Point-In-Time Validation", header_style="bold yellow")
        table.add_column("View", style="bold")
        table.add_column("Status")
        table.add_column("Issues")

        for r in reports:
            status = "[green]PASS[/green]" if r.is_valid else "[red]FAIL[/red]"
            issues = "; ".join(r.issues) if r.issues else "None"
            table.add_row(r.view_name, status, issues)

        console.print(table)

        if summary["invalid"] > 0:
            console.print(f"\n[red]{summary['invalid']} views have issues[/red]")
        else:
            console.print(f"\n[green]All {summary['valid']} views passed validation[/green]")
    finally:
        vm.close()
