"""Stock, Future, Option, Volatility, Volume-Profile CLI commands."""

from __future__ import annotations

from datetime import date, timedelta

from rich.console import Console

from analytics import Analytics
from analytics.reports.reports import print_result

from .analytics_utils import last_float, price_change


def run_symbol_command(command: str, args: list[str], broker_service, console: Console) -> None:
    if not args:
        console.print(f"[yellow]Usage: tradex analytics {command} <symbol>[/yellow]")
        return
    symbol = args[0].upper()
    gateway = broker_service.active_broker
    if not hasattr(gateway, "history"):
        console.print("[red]Active broker does not expose historical data.[/red]")
        return

    to_date = date.today()
    from_date = to_date - timedelta(days=120)
    prices = gateway.history(symbol, timeframe="1D", lookback_days=120, from_date=str(from_date), to_date=str(to_date))
    if prices is None or prices.empty:
        console.print(f"[red]No historical data for {symbol}.[/red]")
        return

    analytics = Analytics()
    if command == "stock":
        benchmark = gateway.history("NIFTY", exchange="INDEX", timeframe="1D", lookback_days=120, from_date=str(from_date), to_date=str(to_date))
        result = analytics.stock(symbol, prices, benchmark_prices=benchmark, benchmark_symbol="NIFTY")
    elif command == "future":
        spot = float(gateway.ltp("NIFTY", exchange="INDEX")) if symbol.upper() == "NIFTY" else None
        future = float(prices["close"].iloc[-1]) if "close" in prices else None
        result = analytics.future(symbol, spot_price=spot, future_price=future, current_oi=last_float(prices, "oi"), price_change=price_change(prices))
    elif command in {"option", "options"}:
        chain = gateway.option_chain(symbol) if hasattr(gateway, "option_chain") else {"strikes": []}
        spot = float(gateway.ltp(symbol, exchange="INDEX")) if symbol.upper() in {"NIFTY", "BANKNIFTY"} else None
        result = analytics.options(symbol, chain, spot_price=spot)
    elif command == "volatility":
        result = analytics.volatility(symbol, prices)
    else:
        result = analytics.volume_profile(prices, symbol=symbol)
    print_result(result, console)
