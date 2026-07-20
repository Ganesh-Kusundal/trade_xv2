"""Unit tests for the Portfolio aggregate (PnL, exposure, concentration)."""

from __future__ import annotations

from decimal import Decimal

from domain.entities.position import Position
from domain.portfolio.portfolio import Portfolio


def _pos(
    symbol: str, qty: int, avg: Decimal, ltp: Decimal, realized: Decimal = Decimal("0")
) -> Position:
    return Position(
        symbol=symbol,
        exchange="NSE",
        quantity=qty,
        avg_price=avg,
        ltp=ltp,
        unrealized_pnl=Decimal(str(qty)) * (ltp - avg) if qty != 0 else Decimal("0"),
        realized_pnl=realized,
    )


def test_empty_portfolio():
    p = Portfolio()
    assert p.position_count == 0
    assert p.total_pnl.to_decimal() == Decimal("0")
    assert p.gross_exposure.to_decimal() == Decimal("0")


def test_single_position_pnl():
    p = Portfolio()
    p.add_position(_pos("RELIANCE", 10, Decimal("2500"), Decimal("2600")))
    assert p.unrealized_pnl.to_decimal() == Decimal("1000")
    assert p.realized_pnl.to_decimal() == Decimal("0")
    assert p.total_pnl.to_decimal() == Decimal("1000")
    assert p.pnl().to_decimal() == Decimal("1000")


def test_multiple_positions_pnl():
    p = Portfolio()
    p.add_position(_pos("RELIANCE", 10, Decimal("2500"), Decimal("2600"), realized=Decimal("200")))
    p.add_position(_pos("TCS", 5, Decimal("3500"), Decimal("3400"), realized=Decimal("100")))
    # R: unrealized = 10*(2600-2500) = 1000, realized=200; TCS: 5*(3400-3500)=-500, realized=100
    assert p.unrealized_pnl.to_decimal() == Decimal("500")  # 1000 - 500
    assert p.realized_pnl.to_decimal() == Decimal("300")  # 200 + 100
    assert p.total_pnl.to_decimal() == Decimal("800")


def test_gross_exposure():
    p = Portfolio()
    p.add_position(_pos("RELIANCE", 10, Decimal("2500"), Decimal("2500")))
    p.add_position(_pos("TCS", 5, Decimal("3500"), Decimal("3500")))
    # R: |2500*10| = 25000; TCS: |3500*5| = 17500; total = 42500
    assert p.gross_exposure.to_decimal() == Decimal("42500")


def test_symbol_exposure_and_concentration():
    p = Portfolio()
    p.add_position(_pos("RELIANCE", 10, Decimal("2500"), Decimal("2500")))
    p.add_position(_pos("TCS", 5, Decimal("3500"), Decimal("3500")))
    r_exposure = p.symbol_exposure("RELIANCE", "NSE")
    assert r_exposure.to_decimal() == Decimal("25000")
    conc = p.concentration("RELIANCE", "NSE")
    assert conc == Decimal("25000") / Decimal("42500")


def test_concentration_empty_portfolio():
    assert Portfolio().concentration("X", "Y") == Decimal("0")


def test_update_ltp_replaces_position():
    p = Portfolio()
    p.add_position(_pos("RELIANCE", 10, Decimal("2500"), Decimal("2500")))
    p.update_ltp("RELIANCE", "NSE", Decimal("2700"))
    pos = p.positions["RELIANCE:NSE"]
    assert pos.ltp.to_decimal() == Decimal("2700")
    assert pos.unrealized_pnl.to_decimal() == Decimal("2000")


def test_remove_position():
    p = Portfolio()
    p.add_position(_pos("RELIANCE", 10, Decimal("2500"), Decimal("2500")))
    p.remove_position("RELIANCE", "NSE")
    assert p.position_count == 0
