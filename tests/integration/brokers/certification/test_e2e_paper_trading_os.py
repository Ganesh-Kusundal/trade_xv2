"""End-to-end Trading OS paper broker flow (SDK + services + certification)."""

from __future__ import annotations

from decimal import Decimal

import pytest

from brokers.certification.golden import verify_golden
from brokers.certification.mapping import verify_mapping
from brokers.certification.market_hours import current_phase, verify_market_hours
from brokers.services import (
    get_quote,
    lookup_security,
    place_order,
    run_connect,
    run_verify,
)
from brokers.session import BrokerSession


@pytest.mark.integration
@pytest.mark.certification
def test_e2e_paper_sdk_flow() -> None:
    session = BrokerSession.connect("paper")
    try:
        assert session.runtime is not None
        assert session.runtime.checkpoints
        stock = session.stock("RELIANCE")
        q = stock.refresh()
        assert q is not None and q.ltp is not None
        series = session.history(stock, timeframe="1D", days=3)
        assert getattr(series, "bar_count", 0) > 0
        handle = session.subscribe(stock)
        assert handle is not None
        session.unsubscribe(stock)
        # Composition surface
        assert hasattr(stock, "history")
        assert hasattr(stock, "subscribe")
        assert hasattr(stock, "capabilities")
    finally:
        session.close()


@pytest.mark.integration
@pytest.mark.certification
def test_e2e_paper_services_parity() -> None:
    info = run_connect("paper")
    assert info["broker_id"] == "paper"
    assert info["checkpoints"]
    q = get_quote("paper", "RELIANCE")
    assert q is not None
    sec = lookup_security("paper", "RELIANCE")
    assert sec["instrument_id"].startswith("NSE:")
    result = place_order("paper", "RELIANCE", 1, price=Decimal("100"), order_type="LIMIT")
    assert result is not None
    report = run_verify("paper")
    assert report.passed, report.steps


@pytest.mark.integration
@pytest.mark.certification
def test_e2e_mapping_golden_market_hours() -> None:
    assert verify_mapping("paper").all_passed
    assert verify_golden("paper").all_passed
    phase = current_phase()
    assert isinstance(phase, str) and phase
    report = verify_market_hours("paper")
    assert report.results
    assert report.all_passed
