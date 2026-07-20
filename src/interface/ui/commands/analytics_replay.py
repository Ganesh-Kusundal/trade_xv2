"""Replay CLI command."""

from __future__ import annotations

import pandas as pd
from rich.console import Console
from rich.table import Table

from analytics.pipeline import ATR, RSI, SMA, FeaturePipeline
from analytics.replay import ReplayConfig
from analytics.strategy import MomentumStrategy, StrategyPipeline


def run_replay(args: list[str], console: Console) -> None:
    """Run historical replay through the same pipeline used in live trading."""
    file_path = None
    symbol = "REPLAY"
    date = None
    warmup = 20
    slippage = 0.01
    commission = 0.0003
    research_only = False
    index = 0
    while index < len(args):
        arg = args[index]
        if arg == "--research":
            research_only = True
            index += 1
        elif arg == "--file" and index + 1 < len(args):
            file_path = args[index + 1]
            index += 2
        elif arg == "--symbol" and index + 1 < len(args):
            symbol = args[index + 1].upper()
            index += 2
        elif arg == "--date" and index + 1 < len(args):
            date = args[index + 1]
            index += 2
        elif arg == "--warmup" and index + 1 < len(args):
            warmup = int(args[index + 1])
            index += 2
        elif arg == "--slippage" and index + 1 < len(args):
            slippage = float(args[index + 1])
            index += 2
        elif arg == "--commission" and index + 1 < len(args):
            commission = float(args[index + 1])
            index += 2
        elif arg == "--speed" and index + 1 < len(args):
            float(args[index + 1])
            index += 2
        else:
            index += 1

    # Load data from file or datalake
    if file_path:
        try:
            data = pd.read_csv(file_path)
            console.print(f"[dim]Loaded {len(data)} bars from {file_path}[/dim]")
        except Exception as exc:
            console.print(f"[red]Error loading file: {exc}[/red]")
            return
    elif symbol and date:
        try:
            from datalake.gateway import DataLakeGateway

            gw = DataLakeGateway()
            data = gw.history(symbol, timeframe="1m", from_date=date, to_date=date)
            if data.empty:
                console.print(f"[red]No data for {symbol} on {date}[/red]")
                return
            console.print(
                f"[dim]Loaded {len(data)} bars from datalake for {symbol} on {date}[/dim]"
            )
        except Exception as exc:
            console.print(f"[red]Error loading from datalake: {exc}[/red]")
            return
    else:
        console.print(
            "[yellow]Usage: tradex analytics replay --file ohlcv.csv [--symbol RELIANCE] [--date 2024-01-15] [--warmup 20] [--slippage 0.01] [--commission 0.0003][/yellow]"
        )
        console.print(
            "[yellow]   OR: tradex analytics replay --symbol RELIANCE --date 2024-01-15[/yellow]"
        )
        return

    required = {"close"}
    missing = required - set(data.columns)
    if missing:
        console.print(f"[red]Missing required columns: {missing}[/red]")
        return

    pipeline = FeaturePipeline().add(RSI(14)).add(ATR(14)).add(SMA(20))
    strategy = StrategyPipeline(strategies=[MomentumStrategy()])
    config = ReplayConfig(
        warmup_bars=warmup,
        slippage_pct=slippage,
        commission_pct=commission,
    )

    console.print(f"[dim]Running replay: {symbol}, {len(data)} bars, warmup={warmup}[/dim]")
    from runtime.paper_session import build_replay_engine

    engine = build_replay_engine(
        pipeline,
        strategy,
        config,
        research_only=research_only,
    )
    if research_only:
        console.print("[yellow]research-only — not OMS parity-backed[/yellow]")
    else:
        console.print("[dim]OMS parity-backed replay session[/dim]")
    result = engine.run(data, symbol=symbol)

    console.print("\n[bold cyan]=== REPLAY RESULTS ===[/bold cyan]\n")

    session = result.session
    console.print(f"[bold]Total Bars:[/bold] {result.total_bars}")
    console.print(f"[bold]Signals Generated:[/bold] {result.signal_count}")
    console.print(f"[bold]Trades Executed:[/bold] {len(session.trades)}")

    if session.trades:
        wins = sum(1 for t in session.trades if t.pnl > 0)
        losses = sum(1 for t in session.trades if t.pnl <= 0)
        console.print(
            f"[bold]Win Rate:[/bold] {wins / (wins + losses) * 100:.1f}%"
            if (wins + losses) > 0
            else "[bold]Win Rate:[/bold] N/A"
        )
        console.print(f"[bold]Total P&L:[/bold] ₹{session.total_pnl:.2f}")
        console.print(f"[bold]Commission:[/bold] ₹{session.total_commission:.2f}")

        # Trade log
        table = Table(title="Trade Log", header_style="bold cyan")
        table.add_column("#", style="dim", width=4)
        table.add_column("Symbol", style="bold white")
        table.add_column("Side", style="cyan")
        table.add_column("Entry", style="green")
        table.add_column("Exit", style="green")
        table.add_column("P&L", style="magenta")
        table.add_column("Strategy", style="yellow")

        for i, trade in enumerate(session.trades[:20], 1):
            pnl_style = "green" if trade.pnl > 0 else "red"
            table.add_row(
                str(i),
                trade.symbol,
                trade.side.value,
                f"₹{trade.entry_price:.2f}",
                f"₹{trade.exit_price:.2f}",
                f"[{pnl_style}]₹{trade.pnl:.2f}[/{pnl_style}]",
                trade.strategy,
            )
        console.print(table)

        if len(session.trades) > 20:
            console.print(f"[dim]... and {len(session.trades) - 20} more trades[/dim]")
    else:
        console.print("\n[yellow]No trades executed.[/yellow]")

    # Open positions
    if session.open_positions:
        console.print(f"\n[bold]Open Positions:[/bold] {len(session.open_positions)}")
        for p in session.open_positions:
            pnl_style = "green" if p.unrealized_pnl >= 0 else "red"
            console.print(
                f"  {p.symbol}: {p.side.value} {p.quantity} @ ₹{p.entry_price:.2f} → ₹{p.current_price:.2f} ([{pnl_style}]₹{p.unrealized_pnl:.2f}[/{pnl_style}])"
            )
