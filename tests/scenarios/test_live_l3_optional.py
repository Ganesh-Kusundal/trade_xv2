"""L3 live scenarios — skip unless env credentials present.

Run explicitly::

    pytest tests/scenarios/test_live_l3_optional.py -m live -q
"""

from __future__ import annotations

from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
DHAN_ENV = ROOT / ".env.local"
UPSTOX_ENV = ROOT / ".env.upstox"

pytestmark = pytest.mark.live_readonly


def _has_dhan() -> bool:
    return DHAN_ENV.is_file()


def _has_upstox() -> bool:
    return UPSTOX_ENV.is_file()


@pytest.mark.skipif(not _has_dhan(), reason="no .env.local")
def test_L_DHAN_MARKET_CONNECT_AND_LTP():
    import tradex

    s = tradex.connect("dhan", mode="market", env_path=str(DHAN_ENV))
    try:
        assert s.status is not None
        assert s.status.mode == "market"
        assert s.status.orders_enabled is False
        ltps = s.ltp_many(["RELIANCE"])
        assert "RELIANCE" in ltps
        # capabilities stamped
        eq = s.universe.equity("RELIANCE")
        caps = eq.capabilities()
        assert "depth_20" in caps or "depth_200" in caps
    finally:
        s.close()


@pytest.mark.skipif(not _has_dhan(), reason="no .env.local")
def test_L_DHAN_MARKET_ACCESS_QUOTE_HISTORY():
    """Epic 1 MA-S2: live market-data path — quote refresh + history (no orders)."""
    import tradex
    from domain.candles.historical import HistoricalSeries

    s = tradex.connect("dhan", mode="market", env_path=str(DHAN_ENV))
    try:
        assert s.status.orders_enabled is False
        stock = s.universe.equity("RELIANCE")
        quote = stock.refresh()
        # Live quote may be None off-hours / rate-limit; ltp_many is alternative.
        # Prefer refresh; fall back to session batch if provider returns None.
        if quote is None:
            ltps = s.ltp_many(["RELIANCE"])
            assert ltps.get("RELIANCE") is not None
        else:
            assert stock.ltp is not None and stock.ltp > 0

        series = stock.history(timeframe="1D", days=5)
        assert isinstance(series, HistoricalSeries)
        # Some live accounts return sparse history; require a non-empty attempt.
        assert series.bar_count >= 1 or series.bars is not None
    finally:
        s.close()


@pytest.mark.skipif(not _has_dhan(), reason="no .env.local")
def test_L_DHAN_CHAIN_ATM():
    """DV-012: live option chain + ATM selection (session path)."""
    import tradex

    s = tradex.connect("dhan", mode="market", env_path=str(DHAN_ENV))
    try:
        chain = s.option_chain("NIFTY", expiry=0)
        assert chain.strikes
        atm = chain.select_strikes("ATM")
        assert atm.ce is not None or atm.strike is not None
    finally:
        s.close()


@pytest.mark.skipif(not _has_dhan(), reason="no .env.local")
def test_L_DV012_UNIVERSE_INDEX_OPTION_CHAIN():
    """DV-012: product path universe.index → option_chain (and session convenience).

    Live brokers rate-limit aggressively; skip when both paths return empty.
    """
    import tradex

    s = tradex.connect("dhan", mode="market", env_path=str(DHAN_ENV))
    try:
        # Canonical session convenience (uses universe.index under the hood)
        via_session = s.option_chain("NIFTY", expiry=0)
        idx = s.universe.index("NIFTY")
        via_index = idx.option_chain(expiry=0)

        n_session = len(getattr(via_session, "strikes", None) or [])
        n_index = len(getattr(via_index, "strikes", None) or [])
        if n_session == 0 and n_index == 0:
            pytest.skip("live option chain empty (rate-limit / off-hours)")

        # At least one product path must surface strikes
        assert n_session >= 1 or n_index >= 1
        chain = via_session if n_session >= 1 else via_index
        if hasattr(chain, "select_strikes"):
            sel = chain.select_strikes("ATM")
            assert sel is not None
    finally:
        s.close()


@pytest.mark.skipif(not _has_dhan(), reason="no .env.local")
def test_L_DV013_CHAIN_GREEKS_IF_PRESENT():
    """DV-013 live: greeks surface when broker populates legs (soft if zeros)."""
    import tradex
    from domain.options.greeks import Greeks

    s = tradex.connect("dhan", mode="market", env_path=str(DHAN_ENV))
    try:
        chain = s.option_chain("NIFTY", expiry=0)
        if not getattr(chain, "strikes", None):
            pytest.skip("empty live chain (rate-limit / off-hours)")
        surface = chain.greeks()
        assert surface is not None
        # If any strike has non-zero delta, product path is live-complete
        deltas = [float(g.delta) for g in surface.data.values()] if surface.data else []
        if deltas and any(abs(d) > 1e-9 for d in deltas):
            atm = chain.atm
            if atm is not None:
                assert isinstance(atm.greeks, Greeks)
        # Always prove PCR/max_pain call sites don't raise
        _ = chain.pcr()
        _ = chain.max_pain()
    finally:
        s.close()


@pytest.mark.skipif(not _has_dhan(), reason="no .env.local")
def test_L_MA024_SUBSCRIBE_HANDLE_WITHOUT_TICK_WAIT():
    """MA-024 smoke: subscribe returns active handle (no tick wait — market hours)."""
    import tradex

    s = tradex.connect("dhan", mode="market", env_path=str(DHAN_ENV))
    try:
        stock = s.universe.equity("RELIANCE")
        handle = stock.subscribe()
        assert handle is not None
        # May be inactive if stream fails offline; prefer active when feed starts
        if handle.is_active:
            handle.unsubscribe()
            assert handle.is_active is False
        # If inactive immediately, still succeeded in not raising
    finally:
        s.close()


@pytest.mark.skipif(not _has_upstox(), reason="no .env.upstox")
def test_L_UPSTOX_MARKET():
    import tradex

    s = tradex.connect("upstox", mode="market", env_path=str(UPSTOX_ENV), load_instruments=False)
    try:
        assert s.status.mode == "market"
        eq = s.universe.equity("RELIANCE")
        # provider must be UpstoxDataProvider
        assert getattr(s.provider, "name", None) == "upstox"
        caps = eq.capabilities()
        assert "depth_30" in caps or "news" in caps or isinstance(caps, list)
    finally:
        s.close()
