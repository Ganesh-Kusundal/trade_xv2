"""Main Textual application class defining the interactive TUI."""

from __future__ import annotations

from typing import ClassVar

from textual.app import App, ComposeResult
from textual.widgets import Footer, Header, TabbedContent, TabPane

from cli.services.broker_service import BrokerService
from cli.services.event_bus_service import EventBusService
from cli.services.oms_service import OmsService
from cli.widgets.broker_console import BrokerConsoleWidget
from cli.widgets.diagnostics_console import DiagnosticsConsoleWidget
from cli.widgets.event_ws_console import EventWsConsoleWidget
from cli.widgets.market_console import MarketConsoleWidget
from cli.widgets.oms_console import OmsConsoleWidget
from cli.widgets.performance_console import PerformanceConsoleWidget


class TradexTuiApp(App):
    """TradeXV2 Interactive Diagnostics TUI Application."""

    CSS_PATH = "tui.tcss"
    BINDINGS: ClassVar[list] = [
        ("q", "quit", "Quit Application"),
        ("r", "refresh_all", "Refresh Active Panel"),
    ]

    def __init__(
        self,
        broker_service: BrokerService,
        oms_service: OmsService,
        event_bus_service: EventBusService,
        **kwargs,
    ):
        super().__init__(**kwargs)
        self._broker_service = broker_service
        self._oms_service = oms_service
        self._event_bus_service = event_bus_service

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)

        with TabbedContent(initial="tab-broker"):
            with TabPane("Broker & Account", id="tab-broker"):
                yield BrokerConsoleWidget(self._broker_service, id="widget-broker")
            with TabPane("OMS & Orders", id="tab-oms"):
                yield OmsConsoleWidget(self._oms_service, id="widget-oms")
            with TabPane("Market Terminal", id="tab-market"):
                yield MarketConsoleWidget(self._broker_service, id="widget-market")
            with TabPane("Events & Websocket", id="tab-events"):
                yield EventWsConsoleWidget(
                    self._broker_service, self._event_bus_service, id="widget-events"
                )
            with TabPane("Doctor Diagnostics", id="tab-doctor"):
                yield DiagnosticsConsoleWidget(self._broker_service, id="widget-doctor")
            with TabPane("Performance Testing", id="tab-stress"):
                yield PerformanceConsoleWidget(self._broker_service, id="widget-stress")

        yield Footer()

    def action_refresh_all(self) -> None:
        """Action handler to manually refresh the currently visible widget panel."""
        tabs = self.query_one(TabbedContent)
        active_id = tabs.active

        if active_id == "tab-broker":
            self.query_one("#widget-broker", BrokerConsoleWidget).refresh_broker_data()
        elif active_id == "tab-oms":
            self.query_one("#widget-oms", OmsConsoleWidget).refresh_oms_data()
        elif active_id == "tab-market":
            self.query_one("#widget-market", MarketConsoleWidget).refresh_market_data()
        elif active_id == "tab-events":
            self.query_one("#widget-events", EventWsConsoleWidget).refresh_ws_event_data()
        elif active_id == "tab-doctor":
            self.query_one("#widget-doctor", DiagnosticsConsoleWidget).execute_diagnostics()
