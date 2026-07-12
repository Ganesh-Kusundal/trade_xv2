"""TUI widget for broker account summary, holdings, and positions."""

from __future__ import annotations

import logging
from decimal import Decimal

from rich.text import Text
from textual.app import ComposeResult
from textual.containers import Container, Grid, Horizontal
from textual.widgets import Button, DataTable, Label, Static

from domain.errors import BrokerNotReadyError
from interface.ui.services.broker_service import BrokerService

logger = logging.getLogger(__name__)


class BrokerConsoleWidget(Static):
    """Interactive broker operations console displaying account limits, positions, and holdings."""

    def __init__(self, broker_service: BrokerService, **kwargs):
        super().__init__(**kwargs)
        self._broker_service = broker_service

    def compose(self) -> ComposeResult:
        with Container(classes="scroll-container"):
            # Account Summary Metrics Cards
            with Container(classes="panel"):
                yield Label("Account Operations & Limits Summary", classes="title")
                with Grid(id="account-metrics-grid"):
                    yield Label("Available Balance", id="lbl-balance", classes="metric-label")
                    yield Label("Rs. 0.00", id="val-balance", classes="metric-value")

                    yield Label("Used Margin", id="lbl-used", classes="metric-label")
                    yield Label("Rs. 0.00", id="val-used", classes="metric-value")

                    yield Label("Realized PnL", id="lbl-realized", classes="metric-label")
                    yield Label("Rs. 0.00", id="val-realized", classes="metric-value")

                    yield Label("Unrealized PnL", id="lbl-unrealized", classes="metric-label")
                    yield Label("Rs. 0.00", id="val-unrealized", classes="metric-value")

            # Active Positions Table
            with Container(classes="panel"):
                yield Label("Active Positions", classes="title")
                yield DataTable(id="positions-table")

            # Demat Holdings Table
            with Container(classes="panel"):
                yield Label("Demat Holdings", classes="title")
                yield DataTable(id="holdings-table")

            with Horizontal():
                yield Button("Refresh Data", variant="primary", id="btn-refresh-broker")

    def on_mount(self) -> None:
        # Style grid
        grid = self.query_one("#account-metrics-grid", Grid)
        grid.styles.grid_size_columns = 4
        grid.styles.grid_size_rows = 2
        grid.styles.height = 8
        grid.styles.padding = 1

        # Configure DataTable schemas
        pos_table = self.query_one("#positions-table", DataTable)
        pos_table.add_columns("Symbol", "Product", "Qty", "Avg Price", "LTP", "PnL")
        pos_table.styles.height = 10

        hld_table = self.query_one("#holdings-table", DataTable)
        hld_table.add_columns("Symbol", "Qty", "Avg Price", "LTP", "PnL")
        hld_table.styles.height = 10

        self.refresh_broker_data()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "btn-refresh-broker":
            self.refresh_broker_data()

    def refresh_broker_data(self) -> None:
        """Fetch current portfolio information and refresh tables."""
        try:
            self._broker_service.active_broker
        except BrokerNotReadyError:
            self.notify("Broker not ready", severity="warning")
            return

        from interface.ui.services.active_session import get_active_session
        from interface.ui.services.market_access import refresh_account

        session = get_active_session(self._broker_service)
        try:
            acct = refresh_account(session)
            limits = acct.funds
            positions = acct.positions
            holdings = acct.holdings

            avail = getattr(limits, "available_balance", 0) if limits else 0
            used = getattr(limits, "used_margin", 0) if limits else 0
            if isinstance(limits, dict):
                avail = limits.get("available_balance", limits.get("available_margin", 0))
                used = limits.get("used_margin", 0)

            realized = sum(getattr(p, "realized_pnl", 0) for p in positions)
            unrealized = sum(getattr(p, "unrealized_pnl", 0) for p in positions)

            self.query_one("#val-balance", Label).update(f"Rs. {float(avail):,.2f}")
            self.query_one("#val-used", Label).update(f"Rs. {float(used):,.2f}")

            def style_pnl(val: Decimal) -> Text:
                if val > 0:
                    return Text(f"Rs. {val:,.2f}", style="bold green")
                if val < 0:
                    return Text(f"Rs. {val:,.2f}", style="bold red")
                return Text(f"Rs. {val:,.2f}", style="white")

            self.query_one("#val-realized", Label).update(style_pnl(Decimal(str(realized))))
            self.query_one("#val-unrealized", Label).update(style_pnl(Decimal(str(unrealized))))

            pos_table = self.query_one("#positions-table", DataTable)
            pos_table.clear()
            for pos in positions:
                p_pnl = getattr(pos, "realized_pnl", 0) + getattr(pos, "unrealized_pnl", 0)
                pnl_style = "bold green" if p_pnl > 0 else ("bold red" if p_pnl < 0 else "white")
                product = getattr(getattr(pos, "product_type", None), "value", str(getattr(pos, "product_type", "")))
                pos_table.add_row(
                    pos.symbol,
                    product,
                    str(pos.quantity),
                    f"{pos.avg_price:,.2f}",
                    f"{getattr(pos, 'ltp', 0):,.2f}",
                    Text(f"Rs. {p_pnl:,.2f}", style=pnl_style),
                )

            hld_table = self.query_one("#holdings-table", DataTable)
            hld_table.clear()
            for hld in holdings:
                h_pnl = getattr(hld, "pnl", 0)
                pnl_style = "bold green" if h_pnl > 0 else ("bold red" if h_pnl < 0 else "white")
                hld_table.add_row(
                    hld.symbol,
                    str(hld.quantity),
                    f"{hld.avg_price:,.2f}",
                    f"{getattr(hld, 'ltp', 0):,.2f}",
                    Text(f"Rs. {h_pnl:,.2f}", style=pnl_style),
                )
        except Exception as exc:
            logger.debug("holdings_display_failed: %s", exc)
        finally:
            session.close()
