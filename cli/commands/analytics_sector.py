"""Sector CLI commands."""

from __future__ import annotations

import pandas as pd
from rich.console import Console
from rich.table import Table

from analytics import Analytics
from analytics.reports.reports import print_result
from analytics.sector import SectorAnalyzer

from .analytics_utils import load_dataframe


def run_breadth(args: list[str], console: Console) -> None:
    """Run breadth analysis."""
    data = load_dataframe(args)
    if data is not None and not data.empty:
        row = data.iloc[-1].to_dict()
        result = Analytics().breadth(row)
    else:
        result = Analytics().breadth({"advances": 1200, "declines": 700, "unchanged": 100, "new_highs": 80, "new_lows": 30})
    print_result(result, console)


def run_sector(args: list[str], console: Console) -> None:
    """Run sector analysis."""
    data = load_dataframe(args)
    if data is not None and not data.empty:
        required = {"sector", "relative_strength"}
        if required.issubset(data.columns):
            result = Analytics().sectors(data)
        else:
            result = Analytics().sectors(pd.DataFrame([{"sector": "BANK", "relative_strength": 1.8}, {"sector": "IT", "relative_strength": -0.4}]))
    else:
        result = Analytics().sectors(pd.DataFrame([{"sector": "BANK", "relative_strength": 1.8}, {"sector": "IT", "relative_strength": -0.4}]))
    print_result(result, console)


def run_sector_rotation(args: list[str], console: Console) -> None:
    """Run sector rotation analysis."""
    from analytics.sector import SectorAnalyzer as SA

    data = load_dataframe(args)
    analyzer = SA()

    if data is not None and not data.empty:
        if "sector" in data.columns and "return_pct" in data.columns:
            returns = data.pivot_table(index=data.index, columns="sector", values="return_pct", aggfunc="first")
            result = analyzer.analyze_rotation(returns)
        else:
            result = analyzer.analyze(data).rotation
    else:
        import numpy as np
        np.random.seed(42)
        dates = pd.date_range("2026-01-01", periods=30, freq="D")
        demo_returns = pd.DataFrame({
            "IT": np.random.randn(30) * 0.02,
            "Finance": np.random.randn(30) * 0.015,
            "Pharma": np.random.randn(30) * 0.018,
            "Auto": np.random.randn(30) * 0.022,
            "FMCG": np.random.randn(30) * 0.01,
            "Metals": np.random.randn(30) * 0.025,
        }, index=dates)
        result = analyzer.analyze_rotation(demo_returns)

    table = Table(title="Sector Rotation Analysis", header_style="bold cyan")
    table.add_column("Sector", style="bold white")
    table.add_column("Phase", style="cyan")
    table.add_column("RS Ratio", style="green")
    table.add_column("Momentum", style="yellow")
    table.add_column("Score", style="magenta")
    table.add_column("Signal", style="bold")

    for s in result.sectors:
        signal_style = "green" if s.signal == "inflow" else "red" if s.signal == "outflow" else "dim"
        table.add_row(
            s.sector,
            s.phase.value,
            f"{s.rs_ratio:.1f}",
            f"{s.rs_momentum:+.1f}%",
            f"{s.score:.1f}",
            f"[{signal_style}]{s.signal}[/{signal_style}]",
        )

    console.print(table)
    console.print(f"\n[bold]Rotation Regime:[/bold] {result.rotation_regime}")
    console.print(f"[bold]Leading:[/bold] {', '.join(result.leading_sectors) if result.leading_sectors else 'None'}")
    console.print(f"[bold]Lagging:[/bold] {', '.join(result.lagging_sectors) if result.lagging_sectors else 'None'}")
    console.print(f"[dim]Breadth: {result.breadth_score:.1f}% of sectors with positive momentum[/dim]")


def run_sector_volume(args: list[str], console: Console) -> None:
    """Run sector volume analysis."""
    data = load_dataframe(args)
    analyzer = SectorAnalyzer()

    if data is not None and not data.empty:
        result = analyzer.analyze_volume(data)
    else:
        console.print("[yellow]Provide --file with OHLCV data (symbol,timestamp,open,high,low,close,volume)[/yellow]")
        return

    if not result.profiles:
        console.print("[yellow]No volume data available.[/yellow]")
        return

    table = Table(title="Sector Volume Analysis", header_style="bold cyan")
    table.add_column("Sector", style="bold white")
    table.add_column("Total Volume", style="green")
    table.add_column("Avg Daily", style="cyan")
    table.add_column("Change %", style="yellow")
    table.add_column("Rel Volume", style="magenta")
    table.add_column("Trend", style="bold")
    table.add_column("Score", style="green")

    for p in result.profiles:
        trend_style = "green" if p.volume_trend == "increasing" else "red" if p.volume_trend == "decreasing" else "dim"
        table.add_row(
            p.sector,
            f"{p.total_volume:,.0f}",
            f"{p.avg_daily_volume:,.0f}",
            f"{p.volume_change_pct:+.1f}%",
            f"{p.relative_volume:.2f}x",
            f"[{trend_style}]{p.volume_trend}[/{trend_style}]",
            f"{p.score:.1f}",
        )

    console.print(table)
    console.print(f"\n[bold]Top Volume:[/bold] {result.top_volume_sector}")
    console.print(f"[bold]Lowest Volume:[/bold] {result.low_volume_sector}")
    console.print(f"[dim]Concentration (HHI): {result.volume_concentration:.4f} | Signal: {result.volume_rotation_signal}[/dim]")


def run_sector_strength(args: list[str], console: Console) -> None:
    """Run sector strength scoring."""
    data = load_dataframe(args)
    analyzer = SectorAnalyzer()

    if data is not None and not data.empty:
        result = analyzer.analyze(data).strength
    else:
        console.print("[yellow]Provide --file with OHLCV data (symbol,timestamp,open,high,low,close,volume,sector)[/yellow]")
        return

    if not result.sectors:
        console.print("[yellow]No sector data available.[/yellow]")
        return

    table = Table(title="Sector Strength Ranking", header_style="bold cyan")
    table.add_column("Rank", style="dim", width=4)
    table.add_column("Sector", style="bold white")
    table.add_column("Score", style="green")
    table.add_column("Momentum", style="cyan")
    table.add_column("Volume", style="yellow")
    table.add_column("Breadth", style="magenta")
    table.add_column("RS", style="blue")
    table.add_column("Trend", style="bold")
    table.add_column("Stocks", style="dim")
    table.add_column("Signal", style="bold")

    for s in result.sectors:
        signal_style = "green" if s.signal == "strong" else "red" if s.signal == "weak" else "dim"
        table.add_row(
            str(s.rank),
            s.sector,
            f"{s.score:.1f}",
            f"{s.momentum_score:.1f}",
            f"{s.volume_score:.1f}",
            f"{s.breadth_score:.1f}",
            f"{s.rs_score:.1f}",
            f"{s.trend_score:.1f}",
            str(s.stock_count),
            f"[{signal_style}]{s.signal}[/{signal_style}]",
        )

    console.print(table)
    console.print(f"\n[bold]Strongest:[/bold] {result.strongest} | [bold]Weakest:[/bold] {result.weakest}")
    console.print(f"[bold]Market Strength:[/bold] {result.market_strength:.1f}/100")
    console.print(f"[dim]{result.rotation_signal}[/dim]")


def run_sector_full(args: list[str], console: Console) -> None:
    """Run full sector analysis (rotation + volume + strength)."""
    data = load_dataframe(args)
    analyzer = SectorAnalyzer()

    if data is not None and not data.empty:
        result = analyzer.analyze(data)
    else:
        import numpy as np
        np.random.seed(42)
        n_days = 30
        dates = pd.date_range("2026-01-01", periods=n_days, freq="D")
        sectors_demo = ["IT", "Finance", "Pharma", "Auto", "FMCG"]
        rows = []
        for sector in sectors_demo:
            close = 100 + np.cumsum(np.random.randn(n_days) * 2)
            vol = np.random.randint(100000, 500000, n_days).astype(float)
            for i, d in enumerate(dates):
                rows.append({
                    "symbol": f"{sector}_IDX", "sector": sector, "timestamp": d,
                    "open": close[i] - 1, "high": close[i] + 2,
                    "low": close[i] - 2, "close": close[i], "volume": vol[i],
                })
        demo_data = pd.DataFrame(rows)
        result = analyzer.analyze(demo_data)

    console.print("[bold cyan]=== SECTOR ANALYSIS SUMMARY ===[/bold cyan]\n")
    console.print(f"[bold]Rotation Regime:[/bold] {result.rotation.rotation_regime}")
    console.print(f"[bold]Leading:[/bold] {', '.join(result.rotation.leading_sectors) if result.rotation.leading_sectors else 'None'}")
    console.print(f"[bold]Lagging:[/bold] {', '.join(result.rotation.lagging_sectors) if result.rotation.lagging_sectors else 'None'}")
    console.print(f"[bold]Market Strength:[/bold] {result.strength.market_strength:.1f}/100")
    console.print(f"[bold]Strongest:[/bold] {result.strength.strongest} | [bold]Weakest:[/bold] {result.strength.weakest}")
    console.print(f"[dim]Volume concentration: {result.volume.volume_concentration:.4f} | Signal: {result.volume.volume_rotation_signal}[/dim]\n")

    if result.strength.sectors:
        table = Table(title="Sector Strength", header_style="bold cyan")
        table.add_column("#", style="dim", width=3)
        table.add_column("Sector", style="bold white")
        table.add_column("Score", style="green")
        table.add_column("Mom", style="cyan")
        table.add_column("Vol", style="yellow")
        table.add_column("Breadth", style="magenta")
        table.add_column("Signal", style="bold")
        for s in result.strength.sectors:
            sig = "green" if s.signal == "strong" else "red" if s.signal == "weak" else "dim"
            table.add_row(str(s.rank), s.sector, f"{s.score:.1f}", f"{s.momentum_score:.1f}",
                          f"{s.volume_score:.1f}", f"{s.breadth_score:.1f}", f"[{sig}]{s.signal}[/{sig}]")
        console.print(table)
