"""UI quote path must consume QuoteSnapshot (event_time / change_pct), not wire Quote."""

from __future__ import annotations

import ast
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

import pytest
from rich.console import Console

from domain.candles.historical import InstrumentRef
from domain.entities.market import QuoteSnapshot
from domain.provenance import DataProvenance
from interface.ui.services.renderers import quote_table, render_quote


_UI_QUOTE_FILES = (
    Path("src/interface/ui/commands/market.py"),
    Path("src/interface/ui/services/renderers.py"),
    Path("src/interface/ui/commands/market_handlers.py"),
)


@pytest.mark.unit
def test_ui_quote_modules_forbid_wire_quote_fields() -> None:
    """Ratchet: product UI must not read Quote.timestamp / Quote.change."""
    banned = {"timestamp", "change"}
    for path in _UI_QUOTE_FILES:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Attribute) and node.attr in banned:
                # Allow non-quote uses (e.g. order.timestamp) via name filter.
                if isinstance(node.value, ast.Name) and node.value.id in {
                    "quote",
                    "q",
                    "snap",
                }:
                    raise AssertionError(
                        f"{path}:{node.lineno} uses wire field quote.{node.attr}"
                    )


@pytest.mark.unit
def test_render_quote_accepts_snapshot() -> None:
    snap = QuoteSnapshot(
        instrument=InstrumentRef(symbol="RELIANCE", exchange="NSE"),
        ltp=Decimal("1303.7"),
        event_time=datetime(2026, 7, 21, 15, 30, tzinfo=timezone.utc),
        provenance=DataProvenance.now("dhan", "test"),
        open=Decimal("1290"),
        high=Decimal("1310"),
        low=Decimal("1285"),
        close=Decimal("1300"),
        volume=1_000_000,
        change_pct=Decimal("0.28"),
    )
    console = Console(record=True, width=80)
    render_quote(console, "RELIANCE", snap, exchange="NSE")
    text = console.export_text()
    assert "1303.7" in text or "1,303.70" in text
    assert "0.28" in text

    tbl = quote_table("RELIANCE", snap, exchange="NSE")
    assert tbl.row_count >= 6
