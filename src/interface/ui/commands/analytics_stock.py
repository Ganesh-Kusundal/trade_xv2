"""Stock, Future, Option, Volatility, Volume-Profile CLI commands."""

from __future__ import annotations

from rich.console import Console

from analytics import Analytics
from analytics.reports.reports import print_result
from domain.symbols import normalize_symbol
from interface.ui.services.active_session import get_active_session
from interface.ui.services.market_access import fetch_history_df, quote_ltp

from .analytics_utils import last_float, price_change


def run_symbol_command(command: str, args: list[str], broker_service, console: Console) -> None:
    if not args:
        console.print(f"[yellow]Usage: tradex analytics {command} <symbol>[/yellow]")
        return
    symbol = normalize_symbol(args[0])
    session = get_active_session(broker_service)
    try:
        prices = fetch_history_df(session, symbol, days=120)
        if prices is None or getattr(prices, "empty", True):
            console.print(f"[red]No historical data for {symbol}.[/red]")
            return

        analytics = Analytics()
        if command == "stock":
            benchmark = fetch_history_df(session, "NIFTY", exchange="INDEX", days=120)
            result = analytics.stock(
                symbol, prices, benchmark_prices=benchmark, benchmark_symbol="NIFTY"
            )
        elif command == "future":
            spot = float(quote_ltp(session, "NIFTY", "INDEX") or 0) if symbol == "NIFTY" else None
            future = float(prices["close"].iloc[-1]) if "close" in prices else None
            result = analytics.future(
                symbol,
                spot_price=spot,
                future_price=future,
                current_oi=last_float(prices, "oi"),
                price_change=price_change(prices),
            )
        elif command in {"option", "options"}:
            gateway = broker_service.active_broker
            chain = (
                gateway.option_chain(symbol)
                if gateway is not None and hasattr(gateway, "option_chain")
                else {"strikes": []}
            )
            spot = (
                float(quote_ltp(session, symbol, "INDEX") or 0)
                if symbol in {"NIFTY", "BANKNIFTY"}
                else None
            )
            result = analytics.options(symbol, chain, spot_price=spot)
        elif command == "volatility":
            result = analytics.volatility(symbol, prices)
        else:
            result = analytics.volume_profile(prices, symbol=symbol)
    finally:
        session.close()
    print_result(result, console)
