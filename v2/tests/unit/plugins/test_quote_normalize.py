"""normalize_quote — venue dict → domain Quote."""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

from domain.entities import Quote
from domain.value_objects import InstrumentId, Price, Quantity
from plugins.brokers.common.quote_normalize import normalize_quote


def test_normalize_quote_builds_domain_quote() -> None:
    iid = InstrumentId.parse("NSE:RELIANCE")
    ts = datetime(2024, 6, 1, 9, 15, tzinfo=timezone.utc)
    quote = normalize_quote(
        {
            "bid": "2500.50",
            "ask": "2501.00",
            "bid_size": "10",
            "ask_size": "5",
            "timestamp": ts.isoformat(),
        },
        instrument_id=iid,
    )
    assert isinstance(quote, Quote)
    assert quote.instrument_id == iid
    assert quote.bid == Price(value=Decimal("2500.50"))
    assert quote.ask == Price(value=Decimal("2501.00"))
    assert quote.bid_size == Quantity(value=Decimal("10"))
    assert quote.ask_size == Quantity(value=Decimal("5"))
    assert quote.timestamp == ts
