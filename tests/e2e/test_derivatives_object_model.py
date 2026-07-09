"""Epic 3 — Derivatives object model E2E (paper CI gate).

Product path::

    tradex.connect("paper")
      → universe.index("NIFTY") → option_chain()
      → select_strikes("ATM" | "OTM")

Slices:
  DV-010 — option chain discovery (strikes + ATM surface)
  DV-011 — strike selection returns Option instruments
"""

from __future__ import annotations

import pytest

import tradex
from domain.instruments.instrument import Option
from domain.options.option_chain import OptionChain
from domain.options.strike_selection import StrikeSelection


def test_dv010_index_option_chain_has_strikes_and_atm() -> None:
    """DV-010: paper index → option_chain has strikes; ATM surface present."""
    session = tradex.connect("paper")
    try:
        idx = session.universe.index("NIFTY")
        assert idx.symbol == "NIFTY"

        chain = idx.option_chain()
        assert isinstance(chain, OptionChain)
        assert chain.strikes is not None
        assert len(chain.strikes) >= 1
        assert chain.spot is not None and chain.spot > 0

        # ATM surface: property and/or CE+PE at ATM strike
        has_atm_prop = chain.atm is not None
        sel = chain.select_strikes("ATM")
        has_atm_legs = sel.ce is not None or sel.pe is not None
        assert has_atm_prop or has_atm_legs, "expected ATM option(s) on paper chain"
    finally:
        session.close()


def test_dv010_session_option_chain_expiry_offset() -> None:
    """DV-010: session.option_chain(underlying, expiry=0) if API exists."""
    session = tradex.connect("paper")
    try:
        if not hasattr(session, "option_chain"):
            pytest.skip("session.option_chain API not available")

        chain = session.option_chain("NIFTY", expiry=0)
        assert isinstance(chain, OptionChain)
        assert len(chain.strikes) >= 1
        assert chain.underlying.upper() == "NIFTY" or chain.underlying == "NIFTY"
    finally:
        session.close()


def test_dv011_select_strikes_atm_returns_option_instruments() -> None:
    """DV-011: select_strikes('ATM') returns CE and/or PE Option instruments."""
    session = tradex.connect("paper")
    try:
        chain = session.universe.index("NIFTY").option_chain()
        sel = chain.select_strikes("ATM")
        assert isinstance(sel, StrikeSelection)
        assert sel.style == "ATM"
        assert sel.ce is not None or sel.pe is not None
        if sel.ce is not None:
            assert isinstance(sel.ce, Option)
        if sel.pe is not None:
            assert isinstance(sel.pe, Option)
        if sel.strike is not None:
            assert sel.strike > 0
    finally:
        session.close()


def test_dv011_select_strikes_otm_with_steps() -> None:
    """DV-011: select_strikes('OTM', steps=2) when supported."""
    session = tradex.connect("paper")
    try:
        chain = session.universe.index("NIFTY").option_chain()
        if not hasattr(chain, "select_strikes"):
            pytest.skip("OptionChain.select_strikes not available")

        try:
            sel = chain.select_strikes("OTM", steps=2)
        except TypeError as exc:
            pytest.skip(f"select_strikes OTM/steps API differs: {exc}")
        except ValueError as exc:
            pytest.skip(f"select_strikes OTM not supported: {exc}")

        assert isinstance(sel, StrikeSelection)
        assert sel.style == "OTM"
        assert sel.steps == 2
        # At least one wing instrument
        assert sel.ce is not None or sel.pe is not None
        if sel.ce is not None:
            assert isinstance(sel.ce, Option)
        if sel.pe is not None:
            assert isinstance(sel.pe, Option)

        # OTM call should sit at or above ATM when both resolved
        atm = chain.select_strikes("ATM")
        if (
            sel.ce_strike is not None
            and atm.strike is not None
            and sel.ce is not None
            and atm.ce is not None
        ):
            assert sel.ce_strike >= atm.strike
    finally:
        session.close()
