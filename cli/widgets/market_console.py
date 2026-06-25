"""TUI widget for market quotes, depth, and option chains."""

from __future__ import annotations

import logging

from rich.text import Text
from textual.app import ComposeResult
from textual.containers import Container, Horizontal, Vertical
from textual.widgets import Button, DataTable, Input, Label, Static

from cli.commands.market import resolve_exchange
from cli.services.broker_service import BrokerService
from brokers.common.connection.errors import BrokerNotReadyError

logger = logging.getLogger(__name__)


class MarketConsoleWidget(Static):
    """Interactive market data console displaying quotes, market depth, option chains, and futures."""

    def __init__(self, broker_service: BrokerService, **kwargs):
        super().__init__(**kwargs)
        self._broker_service = broker_service
        self._current_symbol = "NIFTY"

    def compose(self) -> ComposeResult:
        with Container(classes="scroll-container"):
            # Symbol Search panel
            with Container(classes="panel", id="sym-search-panel"):
                yield Label("Market Instrument Terminal", classes="title")
                with Horizontal():
                    yield Input(
                        value="NIFTY",
                        placeholder="Enter symbol (e.g. RELIANCE, NIFTY)",
                        id="tui-market-symbol",
                    )
                    yield Button("Query Symbol", variant="primary", id="btn-query-market")

            # Quote Card (Left) & Depth Panel (Right)
            with Horizontal(id="quote-depth-container"):
                with Container(classes="panel", id="quote-panel"):
                    yield Label("Real-time Quote Details", classes="title")
                    with Vertical(id="quote-metrics-vert"):
                        yield Label("Symbol: NIFTY", id="q-sym")
                        yield Label("LTP: Rs. 0.00", id="q-ltp")
                        yield Label("Bid Price: Rs. 0.00", id="q-bid")
                        yield Label("Ask Price: Rs. 0.00", id="q-ask")
                        yield Label("Volume: 0", id="q-vol")
                        yield Label("Open Interest: 0", id="q-oi")

                with Container(classes="panel", id="depth-panel"):
                    yield Label("L2 Order Book (Market Depth)", classes="title")
                    yield DataTable(id="depth-table")

            # Option Chain Panel
            with Container(classes="panel"):
                yield Label("Option Chain Grid", classes="title")
                yield DataTable(id="opt-chain-table")

    def on_mount(self) -> None:
        self.query_one("#sym-search-panel", Container).styles.height = 10
        self.query_one("#quote-depth-container", Horizontal).styles.height = 20
        self.query_one("#quote-panel", Container).styles.width = "40%"
        self.query_one("#depth-panel", Container).styles.width = "60%"

        # Configure DataTable
        d_table = self.query_one("#depth-table", DataTable)
        d_table.add_columns("Bid Qty", "Bid Price", "Ask Price", "Ask Qty")
        d_table.styles.height = 7

        opt_table = self.query_one("#opt-chain-table", DataTable)
        opt_table.add_columns("CE OI", "CE Vol", "CE LTP", "Strike", "PE LTP", "PE Vol", "PE OI")
        opt_table.styles.height = 12

        self.refresh_market_data()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "btn-query-market":
            self.update_query_symbol()

    def update_query_symbol(self) -> None:
        symbol_in = self.query_one("#tui-market-symbol", Input).value.strip().upper()
        if symbol_in:
            self._current_symbol = symbol_in
            self.refresh_market_data()

    def refresh_market_data(self) -> None:
        """Fetch quotes, L2 book, and options chain for selected symbol."""
        try:
            broker = self._broker_service.active_broker
        except BrokerNotReadyError:
            self.notify("Broker not ready", severity="warning")
            return
        symbol = self._current_symbol
        exchange = resolve_exchange(symbol)

        # 1. Update Quote - handle Quote dataclass, not DataFrame
        try:
            quote = broker.quote(symbol, exchange)
            if quote is not None:
                self.query_one("#q-sym", Label).update(
                    f"Symbol: [bold yellow]{symbol}[/bold yellow] ({exchange})"
                )
                self.query_one("#q-ltp", Label).update(
                    f"LTP: [bold green]Rs. {quote.ltp:,.2f}[/bold green]"
                )
                self.query_one("#q-bid", Label).update(f"Bid Price: Rs. {quote.bid:,.2f}")
                self.query_one("#q-ask", Label).update(f"Ask Price: Rs. {quote.ask:,.2f}")
                self.query_one("#q-vol", Label).update(f"Volume: {int(quote.volume):,}")
                # OI may not be available on all quotes
                oi_value = getattr(quote, 'oi', None) or 0
                self.query_one("#q-oi", Label).update(f"Open Interest: {int(oi_value):,}")
        except BrokerNotReadyError:
            self.notify("Broker not ready", severity="warning")
        except Exception as exc:
            logger.warning("quote_refresh_failed: %s", exc)
            self.notify("Failed to fetch quote", severity="error")

        # 2. Update Depth - use correct gateway method
        try:
            depth = broker.depth(symbol, exchange)
            d_table = self.query_one("#depth-table", DataTable)
            d_table.clear()
            if depth is not None and (depth.bids or depth.asks):
                max_levels = min(5, max(len(depth.bids), len(depth.asks)))
                for i in range(max_levels):
                    bid = depth.bids[i] if i < len(depth.bids) else None
                    ask = depth.asks[i] if i < len(depth.asks) else None
                    d_table.add_row(
                        f"{bid.quantity:,}" if bid else "-",
                        f"{bid.price:,.2f}" if bid else "-",
                        f"{ask.price:,.2f}" if ask else "-",
                        f"{ask.quantity:,}" if ask else "-",
                    )
        except BrokerNotReadyError:
            self.notify("Broker not ready", severity="warning")
        except Exception as exc:
            logger.warning("depth_refresh_failed: %s", exc)
            self.notify("Failed to fetch depth", severity="error")

        # 3. Update Option Chain - dynamic expiry resolution
        try:
            from datetime import date
            
            # Resolve next valid expiry dynamically
            expiry = None
            try:
                expiries = broker.options.get_expiries(symbol, "NFO")
                today_str = date.today().isoformat()
                future_expiries = sorted([e for e in expiries if e >= today_str])
                expiry = future_expiries[0] if future_expiries else None
            except Exception:
                pass
            
            if not expiry:
                # Fallback: skip option chain if no expiry found
                return
            
            # Get option chain using correct gateway method
            opt_chain = broker.options.get_option_chain(symbol, "NFO", expiry)
            
            # Convert to dict if it's a dataclass
            if hasattr(opt_chain, 'to_dict'):
                opt_chain = opt_chain.to_dict()
            
            if opt_chain and opt_chain.get('strikes'):
                opt_table = self.query_one("#opt-chain-table", DataTable)
                opt_table.clear()
                
                strikes = opt_chain['strikes']
                spot = opt_chain.get('spot', 0)
                
                # Find ATM strike
                atm_strike = min(strikes, key=lambda s: abs(float(s['strike']) - float(spot)))
                atm_strike_val = float(atm_strike['strike'])
                
                all_strikes = sorted([float(s['strike']) for s in strikes])
                median_strike = float(opt_chain.get('spot', 0))
                
                # Show 5 strikes around ATM
                idx = next((i for i, s in enumerate(all_strikes) if abs(s - atm_strike_val) < 0.01), len(all_strikes) // 2)
                visible_strikes = all_strikes[max(0, idx - 2) : min(len(all_strikes), idx + 3)]
                
                for strike in visible_strikes:
                    # Find matching strike in data
                    ce_data = next((s for s in strikes if float(s['strike']) == strike and s.get('option_type') == 'CE'), None)
                    pe_data = next((s for s in strikes if float(s['strike']) == strike and s.get('option_type') == 'PE'), None)
                    
                    is_atm = abs(strike - atm_strike_val) < 0.1
                    ce_itm = strike < atm_strike_val
                    pe_itm = strike > atm_strike_val
                    
                    strike_txt = Text(
                        f"{strike:,.0f}", style="bold yellow" if is_atm else "bold white"
                    )
                    
                    ce_oi = f"{int(ce_data.get('oi', 0)):,}" if ce_data else "-"
                    ce_vol = f"{int(ce_data.get('volume', 0)):,}" if ce_data else "-"
                    ce_ltp = f"{ce_data.get('ltp', 0):,.2f}" if ce_data and ce_data.get('ltp') else "-"
                    ce_ltp_txt = Text(ce_ltp, style="dim green" if ce_itm else "green")
                    
                    pe_oi = f"{int(pe_data.get('oi', 0)):,}" if pe_data else "-"
                    pe_vol = f"{int(pe_data.get('volume', 0)):,}" if pe_data else "-"
                    pe_ltp = f"{pe_data.get('ltp', 0):,.2f}" if pe_data and pe_data.get('ltp') else "-"
                    pe_ltp_txt = Text(pe_ltp, style="dim red" if pe_itm else "red")
                    
                    opt_table.add_row(
                        ce_oi,
                        ce_vol,
                        ce_ltp_txt,
                        strike_txt,
                        pe_ltp_txt,
                        pe_vol,
                        pe_oi,
                    )
        except BrokerNotReadyError:
            self.notify("Broker not ready", severity="warning")
        except Exception as exc:
            logger.warning("option_chain_refresh_failed: %s", exc)
            self.notify("Failed to fetch option chain", severity="error")
