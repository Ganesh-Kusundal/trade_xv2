"""Tests for InstrumentRegistry — canonical instrument resolution, ATM, future chain."""

import pytest
from unittest.mock import MagicMock
from brokers.common.services.instrument_registry import InstrumentRegistry, CanonicalInstrument


class TestCanonicalInstrument:
    def test_is_option(self):
        inst = CanonicalInstrument(
            symbol="NIFTY 25000 CE", exchange="NFO",
            instrument_type="OPTION", option_type="CE",
            strike_price=25000, underlying="NIFTY", expiry="2026-07-30",
        )
        assert inst.is_option is True
        assert inst.is_future is False
        assert inst.is_equity is False

    def test_is_future(self):
        inst = CanonicalInstrument(
            symbol="NIFTY JUL FUT", exchange="NFO",
            instrument_type="FUTURE", expiry="2026-07-30", underlying="NIFTY",
        )
        assert inst.is_future is True
        assert inst.is_option is False

    def test_is_equity(self):
        inst = CanonicalInstrument(
            symbol="RELIANCE", exchange="NSE", instrument_type="EQUITY",
        )
        assert inst.is_equity is True
        assert inst.is_option is False

    def test_canonical_symbol_option(self):
        inst = CanonicalInstrument(
            symbol="NIFTY 25000 CE", exchange="NFO",
            instrument_type="OPTION", option_type="CE",
            strike_price=25000, underlying="NIFTY", expiry="2026-07-30",
        )
        assert inst.canonical_symbol == "NIFTY 2026-07-30 25000 CE"

    def test_canonical_symbol_future(self):
        inst = CanonicalInstrument(
            symbol="NIFTY JUL FUT", exchange="NFO",
            instrument_type="FUTURE", expiry="2026-07-30", underlying="NIFTY",
        )
        assert inst.canonical_symbol == "NIFTY 2026-07-30 FUT"

    def test_canonical_symbol_equity(self):
        inst = CanonicalInstrument(
            symbol="RELIANCE", exchange="NSE", instrument_type="EQUITY",
        )
        assert inst.canonical_symbol == "RELIANCE"

    def test_broker_id_hidden_in_repr(self):
        inst = CanonicalInstrument(
            symbol="RELIANCE", exchange="NSE",
            instrument_type="EQUITY", _broker_id="12345",
        )
        assert "12345" not in repr(inst)


class TestInstrumentRegistry:
    def _make_gateway(self):
        gw = MagicMock()
        gw.search.return_value = [
            {"symbol": "RELIANCE", "exchange": "NSE", "type": "EQUITY", "name": "Reliance Industries", "security_id": "12345"},
            {"symbol": "RELIANCE", "exchange": "NFO", "type": "FUT", "name": "Reliance Future", "security_id": "12346"},
        ]
        gw.option_chain.return_value = {
            "expiry": "2026-07-30",
            "strikes": [
                {"strike": 24800, "ce_ltp": 120.5, "pe_ltp": 45.2, "ce_oi": 50000, "pe_oi": 42000, "option_type": "CE"},
                {"strike": 24800, "ce_ltp": 120.5, "pe_ltp": 45.2, "ce_oi": 50000, "pe_oi": 42000, "option_type": "PE"},
                {"strike": 24900, "ce_ltp": 90.3, "pe_ltp": 55.8, "ce_oi": 45000, "pe_oi": 38000, "option_type": "CE"},
                {"strike": 24900, "ce_ltp": 90.3, "pe_ltp": 55.8, "ce_oi": 45000, "pe_oi": 38000, "option_type": "PE"},
                {"strike": 25000, "ce_ltp": 65.0, "pe_ltp": 80.0, "ce_oi": 60000, "pe_oi": 55000, "option_type": "CE"},
                {"strike": 25000, "ce_ltp": 65.0, "pe_ltp": 80.0, "ce_oi": 60000, "pe_oi": 55000, "option_type": "PE"},
                {"strike": 25100, "ce_ltp": 45.0, "pe_ltp": 110.0, "ce_oi": 40000, "pe_oi": 48000, "option_type": "CE"},
                {"strike": 25100, "ce_ltp": 45.0, "pe_ltp": 110.0, "ce_oi": 40000, "pe_oi": 48000, "option_type": "PE"},
                {"strike": 25200, "ce_ltp": 30.0, "pe_ltp": 150.0, "ce_oi": 35000, "pe_oi": 52000, "option_type": "CE"},
                {"strike": 25200, "ce_ltp": 30.0, "pe_ltp": 150.0, "ce_oi": 35000, "pe_oi": 52000, "option_type": "PE"},
            ],
        }
        gw.future_chain.return_value = {
            "contracts": [
                {"expiry": "2026-07-30", "ltp": 25000.0, "volume": 100000, "oi": 50000, "change": 1.5},
                {"expiry": "2026-08-28", "ltp": 25050.0, "volume": 50000, "oi": 30000, "change": 1.2},
            ],
        }
        return gw

    def test_resolve_cached(self):
        gw = self._make_gateway()
        reg = InstrumentRegistry(gw)
        inst1 = reg.resolve("RELIANCE", "NSE")
        inst2 = reg.resolve("RELIANCE", "NSE")
        assert inst1 is inst2
        assert gw.search.call_count == 1  # cached after first

    def test_resolve_not_found(self):
        gw = self._make_gateway()
        gw.search.return_value = []
        reg = InstrumentRegistry(gw)
        assert reg.resolve("NONEXISTENT") is None

    def test_resolve_required_raises(self):
        gw = self._make_gateway()
        gw.search.return_value = []
        reg = InstrumentRegistry(gw)
        with pytest.raises(ValueError, match="Instrument not found"):
            reg.resolve_required("NONEXISTENT")

    def test_atm_finds_closest_strike(self):
        gw = self._make_gateway()
        reg = InstrumentRegistry(gw)
        result = reg.atm("NIFTY", spot_price=25030)
        # ATM strike should be 25000 (closest to 25030)
        assert result["call"] is not None
        assert result["put"] is not None
        assert result["call"].strike_price == 25000
        assert result["put"].strike_price == 25000
        assert result["call"].option_type == "CE"
        assert result["put"].option_type == "PE"
        assert result["call"].underlying == "NIFTY"
        assert result["call"].exchange == "NFO"

    def test_atm_no_chain(self):
        gw = self._make_gateway()
        gw.option_chain.return_value = {"strikes": []}
        reg = InstrumentRegistry(gw)
        result = reg.atm("NIFTY", spot_price=25000)
        assert result["call"] is None
        assert result["put"] is None

    def test_current_future(self):
        gw = self._make_gateway()
        reg = InstrumentRegistry(gw)
        inst = reg.current_future("NIFTY")
        assert inst is not None
        assert inst.is_future
        assert inst.expiry == "2026-07-30"  # nearest expiry

    def test_current_future_no_contracts(self):
        gw = self._make_gateway()
        gw.future_chain.return_value = {"contracts": []}
        reg = InstrumentRegistry(gw)
        assert reg.current_future("NIFTY") is None

    def test_option_chain(self):
        gw = self._make_gateway()
        reg = InstrumentRegistry(gw)
        chain = reg.option_chain("NIFTY", expiry="2026-07-30")
        assert len(chain) == 10
        assert all("strike" in s for s in chain)

    def test_future_chain(self):
        gw = self._make_gateway()
        reg = InstrumentRegistry(gw)
        chain = reg.future_chain("NIFTY")
        assert len(chain) == 2
        assert all("expiry" in c for c in chain)

    def test_search_filters_by_exchange(self):
        gw = self._make_gateway()
        reg = InstrumentRegistry(gw)
        results = reg.search("RELIANCE", exchange="NSE")
        assert all(i.exchange == "NSE" for i in results)

    def test_search_returns_all(self):
        gw = self._make_gateway()
        reg = InstrumentRegistry(gw)
        results = reg.search("RELIANCE")
        assert len(results) == 2

    def test_to_canonical_maps_fields(self):
        gw = self._make_gateway()
        reg = InstrumentRegistry(gw)
        raw = {
            "symbol": "NIFTY 25000 CE", "exchange": "NFO",
            "type": "OPTION", "option_type": "CE",
            "strike_price": 25000, "expiry": "2026-07-30",
            "underlying": "NIFTY", "lot_size": 50,
            "security_id": "99999",
        }
        inst = reg._to_canonical(raw)
        assert inst.symbol == "NIFTY 25000 CE"
        assert inst._broker_id == "99999"
        assert inst.lot_size == 50
        assert inst.instrument_type == "OPTION"

    def test_load_instruments_called_once(self):
        gw = self._make_gateway()
        reg = InstrumentRegistry(gw)
        reg.resolve("RELIANCE")
        reg.resolve("RELIANCE")
        assert gw.load_instruments.call_count == 1

    def test_load_instruments_failure_logged(self):
        gw = self._make_gateway()
        gw.load_instruments.side_effect = Exception("API down")
        gw.search.return_value = []  # no results when load fails
        reg = InstrumentRegistry(gw)
        inst = reg.resolve("RELIANCE")
        assert inst is None  # doesn't raise, returns None
