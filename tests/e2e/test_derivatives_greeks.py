"""DV-013 — Greeks / PCR / max-pain via product option chain (paper)."""

from __future__ import annotations

from decimal import Decimal

import tradex
from domain.options.greeks import Greeks
from domain.options.surfaces import GreeksSurface


def test_dv013_atm_greeks_delta_on_paper() -> None:
    session = tradex.connect("paper")
    try:
        chain = session.universe.index("NIFTY").option_chain()
        assert chain.spot is not None and chain.spot > 0
        atm = chain.atm
        assert atm is not None
        g = atm.greeks
        assert isinstance(g, Greeks)
        # Paper synthetic ATM ≈ 0.5
        assert Decimal("0.3") <= g.delta <= Decimal("0.7")
        assert atm.delta == g.delta
        assert g.gamma >= 0
        assert g.vega >= 0
    finally:
        session.close()


def test_dv013_greeks_surface_and_pcr_max_pain() -> None:
    session = tradex.connect("paper")
    try:
        chain = session.option_chain("NIFTY", expiry=0)
        surface = chain.greeks()
        assert isinstance(surface, GreeksSurface)
        assert len(surface.data) >= 5

        pcr = chain.pcr()
        assert pcr is not None and pcr > 0

        pain = chain.max_pain()
        assert pain is not None and pain > 0

        # ATM selection CE greeks present
        sel = chain.select_strikes("ATM")
        assert sel.ce is not None
        assert sel.ce.greeks.delta != 0 or sel.ce.greeks.vega >= 0
    finally:
        session.close()


def test_dv013_iv_on_option_legs() -> None:
    session = tradex.connect("paper")
    try:
        chain = session.universe.index("NIFTY").option_chain()
        atm = chain.atm
        assert atm is not None
        # IV may be Decimal or float depending on leg typing
        iv = atm.iv
        assert iv is not None
        assert float(iv) > 0
    finally:
        session.close()
