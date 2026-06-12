"""Tests for the TradeXV2 TUI dashboard interface."""

from __future__ import annotations

import pytest

from cli.services.broker_service import BrokerService
from cli.services.event_bus_service import EventBusService
from cli.services.oms_service import OmsService
from cli.views.tui_app import TradexTuiApp


@pytest.mark.asyncio
async def test_tui_app_navigation():
    """Verify that the TUI initializes and supports tab switching."""
    broker_service = BrokerService()
    oms_service = OmsService(broker_service)
    event_bus_service = EventBusService()

    app = TradexTuiApp(
        broker_service=broker_service,
        oms_service=oms_service,
        event_bus_service=event_bus_service,
    )

    # Run in async test context
    async with app.run_test() as pilot:
        # 1. Verify initial tab
        assert app.query_one("TabbedContent").active == "tab-broker"

        # 2. Switch to OMS tab
        app.query_one("TabbedContent").active = "tab-oms"
        await pilot.pause()
        assert app.query_one("TabbedContent").active == "tab-oms"

        # 3. Switch to Doctor tab
        app.query_one("TabbedContent").active = "tab-doctor"
        await pilot.pause()
        assert app.query_one("TabbedContent").active == "tab-doctor"

        # 4. Quit TUI
        await pilot.press("q")
