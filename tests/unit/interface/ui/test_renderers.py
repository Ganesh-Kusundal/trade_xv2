"""Unit tests for interface.ui.services.renderers."""

from __future__ import annotations

from decimal import Decimal
from types import SimpleNamespace

import pytest
from rich.console import Console

from interface.ui.services.renderers import render_funds, render_quote


@pytest.mark.unit
def test_render_quote_outputs_ltp() -> None:
    console = Console(record=True, width=120)
    quote = SimpleNamespace(
        ltp=Decimal("100.5"),
        open=Decimal("99"),
        high=Decimal("101"),
        low=Decimal("98"),
        close=Decimal("100"),
        volume=1000,
        change=Decimal("0.5"),
    )
    render_quote(console, "RELIANCE", quote)
    out = console.export_text()
    assert "RELIANCE" in out
    assert "100.50" in out or "100.5" in out


@pytest.mark.unit
def test_render_funds_outputs_balance() -> None:
    console = Console(record=True, width=120)
    funds = SimpleNamespace(
        sod_limit=Decimal("100000"),
        available_balance=Decimal("50000"),
        utilized_amount=Decimal("10000"),
        collateral_amount=Decimal("0"),
        withdrawable_balance=Decimal("45000"),
    )
    render_funds(console, funds)
    out = console.export_text()
    assert "Available Balance" in out
    assert "50,000" in out
