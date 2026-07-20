"""HalfTrend CLI commands."""

from __future__ import annotations

import os
from concurrent.futures import ThreadPoolExecutor, as_completed

import pandas as pd
from rich.console import Console
from rich.table import Table

from analytics.backtest import BacktestConfig, BacktestEngine
from analytics.backtest.engine import ResearchMode
from analytics.indicators.halftrend import HalfTrend
from analytics.indicators.halftrend_backtest import HalfTrendStrategy
from analytics.pipeline import ATR, RSI, FeaturePipeline
from analytics.strategy import StrategyPipeline
from datalake.gateway import DataLakeGateway


def run_halftrend(args: list[str], broker_service, console: Console) -> None:
    """Run HalfTrend analysis on a symbol from the datalake."""
    symbol = None
    years = 1
    cooldown = 500
    period = 10
    index = 0
    while index < len(args):
        arg = args[index]
        if arg == "--years" and index + 1 < len(args):
            years = float(args[index + 1])
            index += 2
        elif arg == "--cooldown" and index + 1 < len(args):
            cooldown = int(args[index + 1])
            index += 2
        elif arg == "--period" and index + 1 < len(args):
            period = int(args[index + 1])
            index += 2
        elif not arg.startswith("--"):
            symbol = args[index].upper()
            index += 1
        else:
            index += 1

    if not symbol:
        console.print(
            "[yellow]Usage: tradex analytics halftrend <SYMBOL> [--years 1] [--cooldown 500] [--period 10][/yellow]"
        )
        return

    gw = DataLakeGateway()
    lookback_days = int(years * 365)
    df = gw.history(symbol, timeframe="1m", lookback_days=lookback_days)
    if df.empty:
        console.print(f"[red]No data for {symbol} in datalake.[/red]")
        return

    console.print(f"[dim]Loaded {len(df)} bars for {symbol} ({years}yr, 1m)[/dim]")

    ht = HalfTrend(period=period, atr_period=period, deviation=1.0, cooldown=cooldown)
    result = ht.compute(df)

    signals = result[result["halftrend_signal"] != "HOLD"]
    buys = signals[signals["halftrend_signal"] == "BUY"]
    sells = signals[signals["halftrend_signal"] == "SELL"]

    table = Table(title=f"HalfTrend: {symbol}", header_style="bold cyan")
    table.add_column("Metric", style="bold white")
    table.add_column("Value", style="green")
    table.add_row("Total Bars", str(len(result)))
    table.add_row("BUY Signals", str(len(buys)))
    table.add_row("SELL Signals", str(len(sells)))
    table.add_row("Cooldown", str(cooldown))
    table.add_row("Period", str(period))

    last_dir = result["halftrend_direction"].iloc[-1]
    dir_str = "UP" if last_dir == 1 else "DOWN" if last_dir == -1 else "UNDEFINED"
    table.add_row("Current Trend", dir_str)

    last_close = float(result["close"].iloc[-1])
    last_ht = (
        float(result["halftrend"].iloc[-1]) if pd.notna(result["halftrend"].iloc[-1]) else None
    )
    if last_ht is not None:
        table.add_row("HalfTrend Line", f"{last_ht:.2f}")
        table.add_row("Distance", f"{((last_close - last_ht) / last_ht * 100):+.2f}%")

    console.print(table)

    if not signals.empty:
        recent = signals.tail(10)
        sig_table = Table(title="Recent Signals", header_style="bold cyan")
        sig_table.add_column("Time", style="dim")
        sig_table.add_column("Signal", style="bold")
        sig_table.add_column("Close", style="green")
        sig_table.add_column("HT Line", style="cyan")

        for ts, halftrend_signal, close, halftrend in zip(
            recent["timestamp"],
            recent["halftrend_signal"],
            recent["close"],
            recent["halftrend"],
            strict=False,
        ):
            sig_style = "green" if halftrend_signal == "BUY" else "red"
            ht_val = f"{halftrend:.2f}" if pd.notna(halftrend) else "-"
            sig_table.add_row(
                str(ts) if pd.notna(ts) else "",
                f"[{sig_style}]{halftrend_signal}[/{sig_style}]",
                f"{close:.2f}",
                ht_val,
            )
        console.print(sig_table)


def run_halftrend_scan(args: list[str], console: Console) -> None:
    """Scan universe with HalfTrend indicator and backtest top candidates."""
    top = 10
    years = 1
    cooldown = 500
    max_workers = min(16, (os.cpu_count() or 8) * 2)
    index = 0
    while index < len(args):
        arg = args[index]
        if arg == "--top" and index + 1 < len(args):
            top = int(args[index + 1])
            index += 2
        elif arg == "--years" and index + 1 < len(args):
            years = float(args[index + 1])
            index += 2
        elif arg == "--cooldown" and index + 1 < len(args):
            cooldown = int(args[index + 1])
            index += 2
        elif arg == "--workers" and index + 1 < len(args):
            max_workers = int(args[index + 1])
            index += 2
        else:
            index += 1

    gw = DataLakeGateway()
    symbols = gw.list_symbols()
    lookback_days = int(years * 365)

    console.print(
        f"[dim]Scanning {len(symbols)} symbols with HalfTrend (cooldown={cooldown}, workers={max_workers})...[/dim]"
    )

    def _scan_symbol(sym: str) -> tuple | None:
        try:
            df = gw.history(sym, timeframe="1m", lookback_days=lookback_days)
            if df.empty or len(df) < 100:
                return None
            ht = HalfTrend(period=10, atr_period=10, deviation=1.0, cooldown=cooldown)
            result = ht.compute(df)
            last = result.iloc[-1]
            direction = last.get("halftrend_direction", 0)
            close = float(last.get("close", 0))
            ht_val = (
                float(last.get("halftrend", close)) if pd.notna(last.get("halftrend")) else close
            )
            distance = abs(close - ht_val) / ht_val * 100 if ht_val else 0
            return (sym, direction, close, ht_val, distance, len(df))
        except Exception:
            return None

    scored = []
    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        futures = {pool.submit(_scan_symbol, sym): sym for sym in symbols}
        for done_count, future in enumerate(as_completed(futures), 1):
            if done_count % 100 == 0:
                console.print(f"[dim]  Progress: {done_count}/{len(symbols)}[/dim]")
            result = future.result()
            if result is not None:
                scored.append(result)

    scored.sort(key=lambda x: (-x[4], x[0]))
    top_candidates = scored[:top]

    if not top_candidates:
        console.print("[yellow]No candidates found.[/yellow]")
        return

    table = Table(title=f"HalfTrend Scan — Top {top}", header_style="bold cyan")
    table.add_column("#", style="dim", width=4)
    table.add_column("Symbol", style="bold white")
    table.add_column("Trend", style="bold")
    table.add_column("Close", style="green")
    table.add_column("HT Line", style="cyan")
    table.add_column("Distance", style="yellow")
    table.add_column("Bars", style="dim")

    for i, (sym, direction, close, ht_val, distance, bars) in enumerate(top_candidates, 1):
        trend_style = "green" if direction == 1 else "red" if direction == -1 else "dim"
        trend_str = "UP" if direction == 1 else "DOWN" if direction == -1 else "FLAT"
        table.add_row(
            str(i),
            sym,
            f"[{trend_style}]{trend_str}[/{trend_style}]",
            f"{close:.2f}",
            f"{ht_val:.2f}",
            f"{distance:.2f}%",
            str(bars),
        )
    console.print(table)

    console.print("\n[bold]Backtesting top 5 with HalfTrend strategy...[/bold]")
    pipeline = FeaturePipeline().add(RSI(14)).add(ATR(14))
    strategy = StrategyPipeline(strategies=[HalfTrendStrategy()])
    config = BacktestConfig(initial_capital=100_000, warmup_bars=50)

    bt_table = Table(title="HalfTrend Backtest Results", header_style="bold cyan")
    bt_table.add_column("#", style="dim", width=4)
    bt_table.add_column("Symbol", style="bold white")
    bt_table.add_column("Return", style="green")
    bt_table.add_column("Trades", style="cyan")
    bt_table.add_column("Win Rate", style="yellow")
    bt_table.add_column("Sharpe", style="magenta")

    def _backtest(i_sym: tuple[int, str]) -> tuple[int, str, str, str, str, str]:
        i, sym = i_sym
        try:
            df = gw.history(sym, timeframe="1m", lookback_days=lookback_days)
            if df.empty:
                return (i, sym, "[red]No data[/red]", "-", "-", "-")
            engine = BacktestEngine(
                pipeline, strategy, config, mode=ResearchMode.PURE_SIM
            )
            bt_result = engine.run(df, symbol=sym)
            m = bt_result.metrics
            ret_style = "green" if m.total_return_pct >= 0 else "red"
            return (
                i,
                sym,
                f"[{ret_style}]{m.total_return_pct:+.2f}%[/{ret_style}]",
                str(m.trade_analysis.total_trades),
                f"{m.trade_analysis.win_rate * 100:.0f}%",
                f"{m.sharpe_ratio:.2f}",
            )
        except Exception as e:
            return (i, sym, f"[red]Error: {e}[/red]", "-", "-", "-")

    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        bt_results = list(pool.map(_backtest, enumerate(top_candidates[:5], 1)))

    for row in sorted(bt_results, key=lambda r: r[0]):
        bt_table.add_row(*row[1:])

    console.print(bt_table)
