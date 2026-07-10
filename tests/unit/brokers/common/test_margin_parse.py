"""Shared margin response normalizer."""

from __future__ import annotations

from decimal import Decimal

from brokers.common.oms.margin_provider import parse_margin_response


def test_parse_margin_response_nse_fields():
    result = parse_margin_response(
        {
            "totalMargin": "1500.50",
            "availableMargin": "100000",
            "spanMargin": "900",
            "exposureMargin": "600.5",
        }
    )
    assert result.required_margin == Decimal("1500.50")
    assert result.available_margin == Decimal("100000")
    assert result.span_margin == Decimal("900")
    assert result.exposure_margin == Decimal("600.5")
