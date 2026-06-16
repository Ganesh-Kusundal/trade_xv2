"""TUI widget for Order Management System (OMS) operations."""

from __future__ import annotations

import logging
from decimal import Decimal

from rich.text import Text
from textual.app import ComposeResult
from textual.containers import Container, Horizontal, Vertical
from textual.widgets import Button, DataTable, Input, Label, Select, Static

from cli.services.oms_service import OmsService

logger = logging.getLogger(__name__)


class OmsConsoleWidget(Static):
    """Interactive OMS operations console displaying order book, trade book, and order form."""

    def __init__(self, oms_service: OmsService, **kwargs):
        super().__init__(**kwargs)
        self._oms_service = oms_service

    def compose(self) -> ComposeResult:
        with Container(classes="scroll-container"):
            # Horizontal split: Order Placement Form (Left) & OMS stats (Right)
            with Horizontal(id="oms-form-header"):
                with Container(classes="panel", id="order-form-panel"):
                    yield Label("Test Order Placement Form", classes="title")
                    yield Input(placeholder="Symbol (e.g. RELIANCE)", id="order-symbol")

                    with Horizontal():
                        yield Select(
                            [("BUY", "BUY"), ("SELL", "SELL")], value="BUY", id="order-side"
                        )
                        yield Select(
                            [("MARKET", "MARKET"), ("LIMIT", "LIMIT")],
                            value="LIMIT",
                            id="order-type",
                        )

                    with Horizontal():
                        yield Input(placeholder="Qty (e.g. 10)", id="order-qty")
                        yield Input(placeholder="Price (e.g. 2500)", id="order-price")

                    yield Button("Place Test Order", variant="primary", id="btn-place-order")
                    yield Label("", id="lbl-form-status")

                with Container(classes="panel", id="oms-stats-panel"):
                    yield Label("OMS Order Statistics", classes="title")
                    with Vertical():
                        yield Label("Open Orders: 0", id="stat-open")
                        yield Label("Pending Fills: 0", id="stat-pending")
                        yield Label("Filled Orders: 0", id="stat-filled")
                        yield Label("Rejected Orders: 0", id="stat-rejected")
                        yield Label("Cancelled Orders: 0", id="stat-cancelled")

            # Orders list
            with Container(classes="panel"):
                yield Label("Daily Orders Book", classes="title")
                yield DataTable(id="tui-orders-table")
                with Horizontal():
                    yield Button("Cancel Selected Order", variant="error", id="btn-cancel-order")
                    yield Button("Refresh Orders", id="btn-refresh-orders")

            # Executed Trades
            with Container(classes="panel"):
                yield Label("Executed Trades Book", classes="title")
                yield DataTable(id="tui-trades-table")

    def on_mount(self) -> None:
        # Style layout panels
        self.query_one("#oms-form-header", Horizontal).styles.height = 24
        self.query_one("#order-form-panel", Container).styles.width = "60%"
        self.query_one("#oms-stats-panel", Container).styles.width = "40%"

        # Configure DataTable
        ord_table = self.query_one("#tui-orders-table", DataTable)
        ord_table.add_columns("Order ID", "Symbol", "Side", "Type", "Qty", "Price", "Status")
        ord_table.styles.height = 10
        ord_table.cursor_type = "row"

        trd_table = self.query_one("#tui-trades-table", DataTable)
        trd_table.add_columns("Trade ID", "Symbol", "Side", "Qty", "Price", "Execution Value")
        trd_table.styles.height = 10

        self.refresh_oms_data()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "btn-refresh-orders":
            self.refresh_oms_data()
        elif event.button.id == "btn-place-order":
            self.handle_order_placement()
        elif event.button.id == "btn-cancel-order":
            self.handle_order_cancellation()

    def refresh_oms_data(self) -> None:
        """Fetch orders and trades from service and update widgets."""
        try:
            # Update stats
            stats = self._oms_service.get_order_stats()
            self.query_one("#stat-open", Label).update(
                f"Open Orders: [yellow]{stats['open']}[/yellow]"
            )
            self.query_one("#stat-pending", Label).update(
                f"Pending Fills: [yellow]{stats['pending']}[/yellow]"
            )
            self.query_one("#stat-filled", Label).update(
                f"Filled Orders: [green]{stats['filled']}[/green]"
            )
            self.query_one("#stat-rejected", Label).update(
                f"Rejected Orders: [red]{stats['rejected']}[/red]"
            )
            self.query_one("#stat-cancelled", Label).update(
                f"Cancelled Orders: [dim white]{stats['cancelled']}[/dim white]"
            )

            # Fill Orders table
            orders = self._oms_service.get_orders()
            ord_table = self.query_one("#tui-orders-table", DataTable)
            ord_table.clear()
            for o in orders:
                side_style = "green" if o.side.value == "BUY" else "red"
                if o.status.value == "FILLED":
                    status_style = "green"
                elif o.status.value in ("OPEN", "PARTIALLY_FILLED"):
                    status_style = "yellow"
                elif o.status.value == "CANCELLED":
                    status_style = "dim white"
                else:
                    status_style = "red"

                ord_table.add_row(
                    o.order_id,
                    o.symbol,
                    Text(o.side.value, style=side_style),
                    o.order_type.value,
                    f"{o.filled_quantity}/{o.quantity}",
                    f"{o.price:,.2f}" if o.price > 0 else "MARKET",
                    Text(o.status.value, style=status_style),
                )

            # Fill Trades table
            trades = self._oms_service.get_trades()
            trd_table = self.query_one("#tui-trades-table", DataTable)
            trd_table.clear()
            for t in trades:
                side_style = "green" if t.side.value == "BUY" else "red"
                trd_table.add_row(
                    t.trade_id,
                    t.symbol,
                    Text(t.side.value, style=side_style),
                    str(t.quantity),
                    f"{t.price:,.2f}",
                    f"{t.value:,.2f}",
                )
        except Exception as exc:
            logger.debug("trades_display_failed: %s", exc)

    def handle_order_placement(self) -> None:
        """Read form inputs and execute order placement."""
        symbol_in = self.query_one("#order-symbol", Input).value.strip().upper()
        side_in = self.query_one("#order-side", Select).value
        type_in = self.query_one("#order-type", Select).value
        qty_in = self.query_one("#order-qty", Input).value.strip()
        price_in = self.query_one("#order-price", Input).value.strip()

        status_lbl = self.query_one("#lbl-form-status", Label)

        if not symbol_in or not qty_in:
            status_lbl.update("[red]Error: Symbol and Qty are required[/red]")
            return

        try:
            qty = int(qty_in)
            price = Decimal(price_in) if price_in else Decimal("0.00")

            # Place order via service
            resp = self._oms_service.place_order(
                symbol=symbol_in,
                exchange="NFO" if "CE" in symbol_in or "PE" in symbol_in else "NSE",
                side=side_in,
                quantity=qty,
                price=price,
                order_type=type_in,
            )

            if resp.success:
                status_lbl.update(f"[green]Placed: ID={resp.order_id}[/green]")
                self.refresh_oms_data()
                # Clear inputs
                self.query_one("#order-symbol", Input).value = ""
                self.query_one("#order-qty", Input).value = ""
                self.query_one("#order-price", Input).value = ""
            else:
                status_lbl.update(f"[red]Failed: {resp.message}[/red]")
        except Exception as exc:
            status_lbl.update(f"[red]Error: {exc}[/red]")

    def handle_order_cancellation(self) -> None:
        """Cancel the order currently selected in the DataTable."""
        ord_table = self.query_one("#tui-orders-table", DataTable)
        status_lbl = self.query_one("#lbl-form-status", Label)

        # Get selected row index
        cursor_row = ord_table.cursor_row
        if cursor_row is None:
            status_lbl.update("[red]Select an open order from the table to cancel[/red]")
            return

        # Get the row data (order ID is in column 0)
        try:
            row_data = ord_table.get_row_at(cursor_row)
            order_id = row_data[0]
            success = self._oms_service.cancel_order(order_id)
            if success:
                status_lbl.update(f"[green]Cancelled Order: {order_id}[/green]")
                self.refresh_oms_data()
            else:
                status_lbl.update(f"[red]Could not cancel: {order_id}[/red]")
        except Exception as exc:
            status_lbl.update(f"[red]Cancellation failed: {exc}[/red]")
