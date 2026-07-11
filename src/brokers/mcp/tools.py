"""MCP tool definitions — broker operations for LLM consumption."""

from __future__ import annotations

from brokers.platform_ops import (
    run_benchmark,
    run_certify,
    run_diagnose,
    run_doctor,
    run_health,
    run_mapping,
    run_verify,
)
from brokers.services import (
    cancel_order,
    get_capabilities,
    get_depth,
    get_funds,
    get_history,
    get_holdings,
    get_news,
    get_option_chain,
    get_orders,
    get_positions,
    get_quote,
    lookup_instrument,
    lookup_security,
    lookup_symbol,
    modify_order,
    place_order,
    run_connect,
    run_subscribe_probe,
    safe_serialize,
)


def register_tools(mcp) -> None:
    """Register all broker MCP tools."""

    @mcp.tool()
    def broker_connect(broker: str = "paper") -> dict:
        """Connect to a broker and return session status + startup checkpoints."""
        return run_connect(broker)

    @mcp.tool()
    def broker_quote(symbol: str, broker: str = "paper", exchange: str = "NSE") -> dict:
        """Fetch a live quote for a symbol."""
        q = get_quote(broker, symbol, exchange=exchange)
        return {"symbol": symbol, "broker": broker, "quote": safe_serialize(q)}

    @mcp.tool()
    def broker_history(
        symbol: str,
        broker: str = "paper",
        timeframe: str = "1D",
        days: int = 5,
        exchange: str = "NSE",
    ) -> dict:
        """Fetch historical OHLCV bars for a symbol."""
        series = get_history(broker, symbol, timeframe=timeframe, days=days, exchange=exchange)
        return {
            "symbol": symbol,
            "broker": broker,
            "timeframe": timeframe,
            "bar_count": getattr(series, "bar_count", 0),
        }

    @mcp.tool()
    def broker_subscribe(symbol: str, broker: str = "paper", exchange: str = "NSE") -> dict:
        """Probe live subscription for a symbol (brief connect/disconnect)."""
        ok = run_subscribe_probe(broker, symbol, exchange=exchange)
        return {"symbol": symbol, "broker": broker, "subscribed": ok}

    @mcp.tool()
    def broker_positions(broker: str = "paper") -> dict:
        """Return open positions."""
        return {"broker": broker, "positions": safe_serialize(get_positions(broker))}

    @mcp.tool()
    def broker_holdings(broker: str = "paper") -> dict:
        """Return portfolio holdings."""
        return {"broker": broker, "holdings": safe_serialize(get_holdings(broker))}

    @mcp.tool()
    def broker_funds(broker: str = "paper") -> dict:
        """Return available funds/margin."""
        return {"broker": broker, "funds": safe_serialize(get_funds(broker))}

    @mcp.tool()
    def broker_orders(broker: str = "paper") -> dict:
        """List orders for the session."""
        return {"broker": broker, "orders": safe_serialize(get_orders(broker))}

    @mcp.tool()
    def broker_place_order(
        symbol: str,
        quantity: int,
        broker: str = "paper",
        side: str = "BUY",
        price: float | None = None,
        order_type: str = "LIMIT",
        product_type: str = "INTRADAY",
        exchange: str = "NSE",
    ) -> dict:
        """Place an order via the OMS spine (paper-safe by default)."""
        result = place_order(
            broker,
            symbol,
            quantity,
            side=side,
            price=price,
            order_type=order_type,
            product_type=product_type,
            exchange=exchange,
        )
        return {"broker": broker, "symbol": symbol, "result": safe_serialize(result)}

    @mcp.tool()
    def broker_modify_order(
        order_id: str,
        broker: str = "paper",
        quantity: int | None = None,
        price: float | None = None,
    ) -> dict:
        """Modify an open order."""
        result = modify_order(broker, order_id, quantity=quantity, price=price)
        return {"broker": broker, "order_id": order_id, "result": safe_serialize(result)}

    @mcp.tool()
    def broker_cancel_order(order_id: str, broker: str = "paper") -> dict:
        """Cancel an open order."""
        result = cancel_order(broker, order_id)
        return {"broker": broker, "order_id": order_id, "result": safe_serialize(result)}

    @mcp.tool()
    def broker_option_chain(
        underlying: str, broker: str = "paper", exchange: str = "NSE"
    ) -> dict:
        """Fetch option chain for an underlying."""
        chain = get_option_chain(broker, underlying, exchange=exchange)
        return {
            "underlying": underlying,
            "broker": broker,
            "strikes": len(getattr(chain, "strikes", []) or []),
        }

    @mcp.tool()
    def broker_market_depth(
        symbol: str, broker: str = "paper", exchange: str = "NSE"
    ) -> dict:
        """Fetch market depth for a symbol."""
        depth = get_depth(broker, symbol, exchange=exchange)
        return {"symbol": symbol, "broker": broker, "depth": safe_serialize(depth)}

    @mcp.tool()
    def broker_health(broker: str = "paper") -> dict:
        """Run broker health checks."""
        report = run_health(broker)
        return {"broker": broker, "checks": [vars(c) for c in report.checks]}

    @mcp.tool()
    def broker_capabilities(broker: str = "paper", symbol: str = "RELIANCE") -> dict:
        """List broker capabilities for an instrument."""
        caps = get_capabilities(broker, symbol)
        return {"broker": broker, "capabilities": safe_serialize(caps)}

    @mcp.tool()
    def broker_symbol_lookup(
        symbol: str, broker: str = "paper", exchange: str = "NSE"
    ) -> dict:
        """Resolve symbol to canonical instrument id."""
        return {
            "symbol": symbol,
            "broker": broker,
            "instrument_id": lookup_symbol(broker, symbol, exchange=exchange),
        }

    @mcp.tool()
    def broker_instrument_lookup(
        symbol: str, broker: str = "paper", exchange: str = "NSE"
    ) -> dict:
        """Resolve symbol to public instrument metadata (symbol, exchange, lot_size)."""
        return lookup_instrument(broker, symbol, exchange=exchange)

    @mcp.tool()
    def broker_news(
        broker: str = "paper",
        symbol: str | None = None,
        category: str = "holdings",
    ) -> dict:
        """Fetch broker news feed (Upstox when configured)."""
        items = get_news(broker, symbol=symbol, category=category)
        return {"broker": broker, "news": safe_serialize(items)}

    @mcp.tool()
    def broker_verify(broker: str = "paper") -> dict:
        """Run startup self-test (config→auth→caps→mappings→quote→history→ws)."""
        return run_verify(broker).to_dict()

    @mcp.tool()
    def broker_doctor(broker: str = "paper") -> dict:
        """Run full environment pre-flight validation."""
        return run_doctor(broker).to_dict()

    @mcp.tool()
    def broker_diagnose(broker: str = "paper") -> dict:
        """Run diagnostics suite (connectivity, auth, data, orders) — TOS-P4-002."""
        result = run_diagnose(broker)
        return {"broker": broker, "diagnostics": safe_serialize(result)}

    @mcp.tool()
    def broker_benchmark(broker: str = "paper") -> dict:
        """Run broker performance benchmark — TOS-P4-002 platform_ops parity."""
        result = run_benchmark(broker)
        return {"broker": broker, "benchmark": safe_serialize(result)}

    @mcp.tool()
    def broker_certify(broker: str = "paper") -> dict:
        """Run full broker certification suite."""
        return run_certify(broker).to_dict()

    @mcp.tool()
    def broker_mappings(broker: str = "paper") -> dict:
        """Run symbol mapping round-trip validation."""
        report = run_mapping(broker)
        return {
            "broker": broker,
            "all_passed": report.all_passed,
            "results": [
                {
                    "asset": r.asset,
                    "exchange": r.exchange,
                    "symbol": r.symbol,
                    "passed": r.passed,
                    "detail": r.detail,
                }
                for r in report.results
            ],
        }
