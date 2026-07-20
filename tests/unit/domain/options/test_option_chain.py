"""Tests for new OptionChain — pure domain object."""

from __future__ import annotations

from decimal import Decimal

from domain.entities.options import OptionChain as OptionChainVO
from domain.entities.options import OptionLeg, OptionStrike
from domain.instruments.instrument import Option
from domain.options.option_chain import OptionChain


def _make_chain(
    underlying="NIFTY",
    exchange="NFO",
    expiry="2026-07-31",
    spot=Decimal("25000"),
    strikes=None,
):
    """Create a test option chain with realistic data."""
    if strikes is None:
        strikes = [
            (
                Decimal("24800"),
                Decimal("80"),
                Decimal("0.3"),
                50000,
                Decimal("300"),
                Decimal("0.6"),
                60000,
            ),
            (
                Decimal("24900"),
                Decimal("60"),
                Decimal("0.4"),
                70000,
                Decimal("180"),
                Decimal("0.5"),
                80000,
            ),
            (
                Decimal("25000"),
                Decimal("40"),
                Decimal("0.5"),
                100000,
                Decimal("40"),
                Decimal("0.5"),
                100000,
            ),
            (
                Decimal("25100"),
                Decimal("25"),
                Decimal("0.6"),
                80000,
                Decimal("60"),
                Decimal("0.4"),
                70000,
            ),
            (
                Decimal("25200"),
                Decimal("15"),
                Decimal("0.7"),
                60000,
                Decimal("100"),
                Decimal("0.3"),
                50000,
            ),
        ]

    strike_objects = []
    for strike, ce_ltp, ce_iv, ce_oi, pe_ltp, pe_iv, pe_oi in strikes:
        ce_leg = OptionLeg(
            ltp=ce_ltp,
            oi=ce_oi,
            iv=ce_iv,
            greeks={"delta": "0.5", "gamma": "0.02", "theta": "-0.1", "vega": "0.3", "rho": "0.01"},
        )
        pe_leg = OptionLeg(
            ltp=pe_ltp,
            oi=pe_oi,
            iv=pe_iv,
            greeks={
                "delta": "-0.5",
                "gamma": "0.02",
                "theta": "-0.1",
                "vega": "0.3",
                "rho": "0.01",
            },
        )
        strike_objects.append(OptionStrike(strike=strike, call=ce_leg, put=pe_leg))

    return OptionChainVO(
        underlying=underlying,
        exchange=exchange,
        expiry=expiry,
        spot=spot,
        strikes=strike_objects,
    )


# ══════════════════════════════════════════════════════════════════════
# Identity
# ══════════════════════════════════════════════════════════════════════


class TestOptionChainIdentity:
    def test_underlying(self):
        chain = OptionChain(_make_chain())
        assert chain.underlying == "NIFTY"

    def test_exchange(self):
        chain = OptionChain(_make_chain())
        assert chain.exchange == "NFO"

    def test_expiry(self):
        chain = OptionChain(_make_chain())
        assert chain.expiry == "2026-07-31"

    def test_spot(self):
        chain = OptionChain(_make_chain(spot=Decimal("25000")))
        assert chain.spot == Decimal("25000")

    def test_strikes(self):
        chain = OptionChain(_make_chain())
        assert len(chain.strikes) == 5

    def test_repr(self):
        chain = OptionChain(_make_chain())
        assert "NIFTY" in repr(chain)


# ══════════════════════════════════════════════════════════════════════
# ATM
# ══════════════════════════════════════════════════════════════════════


class TestATM:
    def test_atm_returns_option(self):
        chain = OptionChain(_make_chain())
        atm = chain.atm
        assert isinstance(atm, Option)

    def test_atm_strike_is_nearest_to_spot(self):
        chain = OptionChain(_make_chain(spot=Decimal("25000")))
        atm = chain.atm
        assert atm.strike == Decimal("25000")

    def test_atm_is_call(self):
        chain = OptionChain(_make_chain())
        atm = chain.atm
        assert atm.right == "CE"

    def test_atm_greeks(self):
        chain = OptionChain(_make_chain())
        atm = chain.atm
        assert atm.greeks is not None

    def test_atm_none_when_no_strikes(self):
        vo = OptionChainVO(underlying="NIFTY", exchange="NFO", expiry="", spot=None, strikes=[])
        chain = OptionChain(vo)
        assert chain.atm is None


# ══════════════════════════════════════════════════════════════════════
# Calls / Puts
# ══════════════════════════════════════════════════════════════════════


class TestCallsPuts:
    def test_calls_returns_list_of_options(self):
        chain = OptionChain(_make_chain())
        calls = chain.calls
        assert len(calls) == 5
        assert all(isinstance(c, Option) for c in calls)

    def test_calls_are_CE(self):
        chain = OptionChain(_make_chain())
        for c in chain.calls:
            assert c.right == "CE"

    def test_puts_returns_list_of_options(self):
        chain = OptionChain(_make_chain())
        puts = chain.puts
        assert len(puts) == 5
        assert all(isinstance(p, Option) for p in puts)

    def test_puts_are_PE(self):
        chain = OptionChain(_make_chain())
        for p in chain.puts:
            assert p.right == "PE"

    def test_calls_strikes_are_sorted(self):
        chain = OptionChain(_make_chain())
        strikes = [c.strike for c in chain.calls]
        assert strikes == sorted(strikes)

    def test_puts_strikes_are_sorted(self):
        chain = OptionChain(_make_chain())
        strikes = [p.strike for p in chain.puts]
        assert strikes == sorted(strikes)


# ══════════════════════════════════════════════════════════════════════
# PCR
# ══════════════════════════════════════════════════════════════════════


class TestPCR:
    def test_pcr_computes_ratio(self):
        chain = OptionChain(_make_chain())
        pcr = chain.pcr()
        assert pcr is not None
        assert pcr > 0

    def test_pcr_uses_oi(self):
        # CE OI: 50000+70000+100000+80000+60000 = 360000
        # PE OI: 60000+80000+100000+70000+50000 = 360000
        # PCR = 360000/360000 = 1.0
        chain = OptionChain(_make_chain())
        assert chain.pcr() == Decimal("1")

    def test_pcr_none_when_no_strikes(self):
        vo = OptionChainVO(underlying="NIFTY", exchange="NFO", expiry="", spot=None, strikes=[])
        chain = OptionChain(vo)
        assert chain.pcr() is None


# ══════════════════════════════════════════════════════════════════════
# Max Pain
# ══════════════════════════════════════════════════════════════════════


class TestMaxPain:
    def test_max_pain_returns_decimal(self):
        chain = OptionChain(_make_chain())
        mp = chain.max_pain()
        assert isinstance(mp, Decimal)

    def test_max_pain_is_one_of_the_strikes(self):
        chain = OptionChain(_make_chain())
        mp = chain.max_pain()
        strikes = [s.strike for s in chain.strikes]
        assert mp in strikes

    def test_max_pain_none_when_no_strikes(self):
        vo = OptionChainVO(underlying="NIFTY", exchange="NFO", expiry="", spot=None, strikes=[])
        chain = OptionChain(vo)
        assert chain.max_pain() is None


# ══════════════════════════════════════════════════════════════════════
# ITM / OTM
# ══════════════════════════════════════════════════════════════════════


class TestITMOTM:
    def test_itm_calls(self):
        chain = OptionChain(_make_chain(spot=Decimal("25000")))
        itm = chain.itm(side="CE")
        # ITM calls: strike < spot (24800, 24900)
        assert len(itm) == 2
        assert all(c.strike < Decimal("25000") for c in itm)

    def test_otm_calls(self):
        chain = OptionChain(_make_chain(spot=Decimal("25000")))
        otm = chain.otm(side="CE")
        # OTM calls: strike > spot (25100, 25200)
        assert len(otm) == 2
        assert all(c.strike > Decimal("25000") for c in otm)

    def test_itm_puts(self):
        chain = OptionChain(_make_chain(spot=Decimal("25000")))
        itm = chain.itm(side="PE")
        # ITM puts: strike > spot (25100, 25200)
        assert len(itm) == 2

    def test_otm_puts(self):
        chain = OptionChain(_make_chain(spot=Decimal("25000")))
        otm = chain.otm(side="PE")
        # OTM puts: strike < spot (24800, 24900)
        assert len(otm) == 2


# ══════════════════════════════════════════════════════════════════════
# Empty Chain
# ══════════════════════════════════════════════════════════════════════


class TestEmptyChain:
    def test_empty_chain(self):
        chain = OptionChain.empty()
        assert chain.underlying == ""
        assert chain.calls == []
        assert chain.puts == []
        assert chain.atm is None
        assert chain.pcr() is None
        assert chain.max_pain() is None
