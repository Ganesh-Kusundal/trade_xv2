"""TUI widget for market quotes, depth, and option chains."""

from __future__ import annotations

from rich.text import Text
from textual.app import ComposeResult
from textual.containers import Container, Horizontal, Vertical
from textual.widgets import Button, DataTable, Input, Label, Static

from cli.commands.market import resolve_exchange
from cli.services.broker_service import BrokerService


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
        broker = self._broker_service.active_broker
        symbol = self._current_symbol
        exchange = resolve_exchange(symbol)

        # 1. Update Quote
        try:
            q_df = broker.get_quote(symbol, exchange)
            if q_df is not None and not q_df.empty:
                row = q_df.iloc[0]
                self.query_one("#q-sym", Label).update(
                    f"Symbol: [bold yellow]{symbol}[/bold yellow] ({exchange})"
                )
                self.query_one("#q-ltp", Label).update(
                    f"LTP: [bold green]Rs. {row['ltp']:,.2f}[/bold green]"
                )
                self.query_one("#q-bid", Label).update(f"Bid Price: Rs. {row['bid']:,.2f}")
                self.query_one("#q-ask", Label).update(f"Ask Price: Rs. {row['ask']:,.2f}")
                self.query_one("#q-vol", Label).update(f"Volume: {int(row['volume']):,}")
                self.query_one("#q-oi", Label).update(f"Open Interest: {int(row['oi']):,}")
        except Exception:
            pass

        # 2. Update Depth
        try:
            d_df = broker.get_market_depth(symbol, exchange)
            d_table = self.query_one("#depth-table", DataTable)
            d_table.clear()
            if d_df is not None and not d_df.empty:
                row = d_df.iloc[0]
                # Print 5 levels
                for i in range(1, 6):
                    d_table.add_row(
                        f"{int(row.get(f'bid_qty_{i}', 0)):,}",
                        f"{row.get(f'bid_price_{i}', 0.0):,.2f}",
                        f"{row.get(f'ask_price_{i}', 0.0):,.2f}",
                        f"{int(row.get(f'ask_qty_{i}', 0)):,}",
                    )
        except Exception:
            pass

        # 3. Update Option Chain (For underlying index or equity)
        try:
            opt_df = broker.get_option_chain(symbol, "NFO", "2026-06-16")
            opt_table = self.query_one("#opt-chain-table", DataTable)
            opt_table.clear()
            if opt_df is not None and not opt_df.empty:
                ce_df = opt_df[opt_df["option_type"] == "CE"].set_index("strike")
                pe_df = opt_df[opt_df["option_type"] == "PE"].set_index("strike")

                median_strike = float(opt_df["strike"].median())
                all_strikes = sorted(set(opt_df["strike"]))

                # Show 5 strikes
                idx = len(all_strikes) // 2
                visible_strikes = all_strikes[max(0, idx - 2) : min(len(all_strikes), idx + 3)]

                for strike in visible_strikes:
                    ce_row = ce_df.loc[strike] if strike in ce_df.index else None
                    pe_row = pe_df.loc[strike] if strike in pe_df.index else None

                    is_atm = abs(strike - median_strike) < 0.1
                    ce_itm = strike < median_strike
                    pe_itm = strike > median_strike

                    strike_txt = Text(
                        f"{strike:,.0f}", style="bold yellow" if is_atm else "bold white"
                    )

                    ce_oi = f"{int(ce_row['oi']):,}" if ce_row is not None else "-"
                    ce_vol = f"{int(ce_row['volume']):,}" if ce_row is not None else "-"
                    ce_ltp = f"{ce_row['ltp']:,.2f}" if ce_row is not None else "-"
                    ce_ltp_txt = Text(ce_ltp, style="dim green" if ce_itm else "green")

                    pe_oi = f"{int(pe_row['oi']):,}" if pe_row is not None else "-"
                    pe_vol = f"{int(pe_row['volume']):,}" if pe_row is not None else "-"
                    pe_ltp = f"{pe_row['ltp']:,.2f}" if pe_row is not None else "-"
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
        except Exception:
            pass
