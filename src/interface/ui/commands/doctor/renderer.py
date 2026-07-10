"""Result renderer for doctor diagnostic output.

Handles table formatting, status color coding, and summary rendering
using Rich.
"""

from __future__ import annotations

from rich.console import Console
from rich.table import Table

from interface.ui.commands.doctor.checks import CheckResult


def _status_str(status: str) -> str:
    """Convert a status string to Rich-colored markup.

    Parameters
    ----------
    status : str
        One of "PASS", "WARN", "FAIL", "INFO", "ERROR".

    Returns
    -------
    str
        Rich markup string with appropriate color.
    """
    if status == "PASS":
        return "[green]PASS[/green]"
    if status == "WARN":
        return "[yellow]WARN[/yellow]"
    if status == "INFO":
        return "[dim]INFO[/dim]"
    if status == "ERROR":
        return "[red]ERROR[/red]"
    return "[red]FAIL[/red]"


class ResultRenderer:
    """Renders diagnostic check results as formatted tables.

    Parameters
    ----------
    console : Console
        Rich console instance for output.

    Example
    -------
    >>> renderer = ResultRenderer(console)
    >>> renderer.render_section("Market Data", results)
    >>> renderer.render_summary(all_results)
    """

    def __init__(self, console: Console) -> None:
        self._console = console

    def render_section(
        self,
        title: str,
        results: list[CheckResult],
        *,
        show_header: bool = True,
    ) -> None:
        """Render a diagnostics table for a group of checks.

        Parameters
        ----------
        title : str
            Section title displayed above the table.
        results : list[CheckResult]
            Check results to display.
        show_header : bool
            Whether to show column headers.
        """
        if not results:
            return
        table = Table(
            title=title,
            header_style="bold cyan",
            show_header=show_header,
            title_justify="left",
        )
        table.add_column("Check", style="bold white", width=32)
        table.add_column("Status", justify="center", width=8)
        table.add_column("Detail", style="dim white", width=72)
        for r in results:
            table.add_row(r.name, _status_str(r.status), r.detail)
        self._console.print(table)
        self._console.print()

    def render_sections(
        self,
        sections: list[tuple[str, list[CheckResult]]],
    ) -> None:
        """Render multiple sections in order.

        Parameters
        ----------
        sections : list[tuple[str, list[CheckResult]]]
            List of (title, results) tuples.
        """
        for title, results in sections:
            self.render_section(title, results)

    def render_summary(self, all_results: list[CheckResult]) -> None:
        """Render the summary line showing pass/warn/fail counts.

        Parameters
        ----------
        all_results : list[CheckResult]
            All check results to summarize.
        """
        n_pass = sum(1 for r in all_results if r.status == "PASS")
        n_warn = sum(1 for r in all_results if r.status == "WARN")
        n_fail = sum(1 for r in all_results if r.status == "FAIL")
        n_info = sum(1 for r in all_results if r.status == "INFO")
        n_error = sum(1 for r in all_results if r.status == "ERROR")
        total = len(all_results)

        self._console.print()
        summary_parts = [
            f"[green]{n_pass} passed[/green]",
            f"[yellow]{n_warn} warnings[/yellow]" if n_warn else None,
            f"[red]{n_fail} failed[/red]" if n_fail else None,
            f"[red]{n_error} error(s)[/red]" if n_error else None,
            f"[dim]{n_info} info[/dim]" if n_info else None,
        ]
        summary_str = " | ".join(p for p in summary_parts if p)
        self._console.print(
            f"[bold]Summary:[/bold] {summary_str}  [dim]({total} checks total)[/dim]"
        )
        self._console.print()
