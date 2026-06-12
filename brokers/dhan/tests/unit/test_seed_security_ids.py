"""Regression tests for the Dhan seed security ID mappings.

These tests pin the values in
``brokers.dhan.mapper.seed_security_ids.DHAN_SEED_SECURITY_IDS`` so that an
accidental drift (or a copy-paste typo from the original Java reference) is
caught immediately.

The values are also asserted in the two consumer code paths that read them:
* ``brokers.common.core.instruments.InstrumentRegistry`` (the canonical engine)
* ``brokers.dhan.mapper.instruments.DhanInstrumentResolver`` (the legacy
  resolver)

So if any of the three drifts away from the others, these tests fail.
"""

from __future__ import annotations

import pytest

from brokers.common.core.enums import ExchangeSegment, InstrumentType
from brokers.common.core.instruments import InstrumentRegistry
from brokers.dhan.mapper.instruments import DhanInstrumentResolver
from brokers.dhan.mapper.seed_security_ids import (
    BANKNIFTY_IDX_SID,
    DHAN_SEED_SECURITY_IDS,
    FINNIFTY_IDX_SID,
    HDFCBANK_NSE_SID,
    INFY_NSE_SID,
    MIDCPNIFTY_IDX_SID,
    NIFTY_IDX_SID,
    NIFTYNXT50_IDX_SID,
    RELIANCE_NSE_SID,
    SBIN_NSE_SID,
    SENSEX_IDX_SID,
    TCS_NSE_SID,
)

# (symbol, exchange) → expected security_id
EXPECTED_NSE_EQUITY = {
    "ADANIENT": "25",
    "ADANIPORTS": "15083",
    "APOLLOHOSP": "157",
    "ASIANPAINT": "236",
    "AXISBANK": "5900",
    "BAJAJ-AUTO": "16669",
    "BAJFINANCE": "317",
    "BAJAJFINSV": "16675",
    "BPCL": "526",
    "BHARTIARTL": "10604",
    "BRITANNIA": "547",
    "CIPLA": "694",
    "COALINDIA": "20374",
    "DIVISLAB": "10940",
    "DRREDDY": "881",
    "EICHERMOT": "910",
    "GRASIM": "1232",
    "HCLTECH": "7229",
    "HDFCBANK": HDFCBANK_NSE_SID,  # 1333
    "HDFCLIFE": "467",
    "HEROMOTOCO": "1348",
    "HINDALCO": "1363",
    "HINDUNILVR": "1394",
    "ICICIBANK": "4963",
    "INDUSINDBK": "5258",
    "INFY": INFY_NSE_SID,  # 1594
    "ITC": "1660",
    "JSWSTEEL": "11723",
    "KOTAKBANK": "1922",
    "LT": "11483",
    "M&M": "2031",
    "MARUTI": "10999",
    "NESTLEIND": "17963",
    "NTPC": "11630",
    "ONGC": "2475",
    "POWERGRID": "14977",
    "RELIANCE": RELIANCE_NSE_SID,  # 2885
    "SBILIFE": "21808",
    "SBIN": SBIN_NSE_SID,  # 3045
    "SUNPHARMA": "3351",
    "TCS": TCS_NSE_SID,  # 11536
    "TATACONSUM": "3432",
    "TATASTEEL": "3499",
    "TECHM": "13538",
    "TITAN": "3506",
    "ULTRACEMCO": "11532",
    "UPL": "11287",
    "WIPRO": "3787",
    "HEG": "1336",
}

EXPECTED_NSE_INDICES = {
    "NIFTY": NIFTY_IDX_SID,  # 13
    "BANKNIFTY": BANKNIFTY_IDX_SID,  # 25
    "FINNIFTY": FINNIFTY_IDX_SID,  # 27
    "MIDCPNIFTY": MIDCPNIFTY_IDX_SID,  # 442
    "SENSEX": SENSEX_IDX_SID,  # 51
    "NIFTYNXT50": NIFTYNXT50_IDX_SID,  # 38
}

EXPECTED_BSE_EQUITY = {
    "RELIANCE": "500325",
    "TCS": "532540",
    "HDFCBANK": "500180",
    "SBIN": "500112",
    "INFY": "500209",
}


class TestDhanSeedSecurityIds:
    """Pin the verified Dhan v2 security IDs."""

    def test_constants_have_expected_values(self):
        """Well-known IDs should match the verified Dhan master."""
        assert RELIANCE_NSE_SID == "2885"
        assert TCS_NSE_SID == "11536"
        assert SBIN_NSE_SID == "3045"
        assert INFY_NSE_SID == "1594"
        assert HDFCBANK_NSE_SID == "1333"
        assert NIFTY_IDX_SID == "13"
        assert BANKNIFTY_IDX_SID == "25"
        assert FINNIFTY_IDX_SID == "27"
        assert NIFTYNXT50_IDX_SID == "38"
        assert MIDCPNIFTY_IDX_SID == "442"
        assert SENSEX_IDX_SID == "51"

    def test_nse_equity_seed_table(self):
        for symbol, expected_sid in EXPECTED_NSE_EQUITY.items():
            assert DHAN_SEED_SECURITY_IDS[(symbol, "NSE")] == expected_sid, (
                f"{symbol} NSE: expected {expected_sid}, "
                f"got {DHAN_SEED_SECURITY_IDS.get((symbol, 'NSE'))!r}"
            )

    def test_nse_indices_seed_table(self):
        for symbol, expected_sid in EXPECTED_NSE_INDICES.items():
            assert DHAN_SEED_SECURITY_IDS[(symbol, "IDX")] == expected_sid, (
                f"{symbol} IDX: expected {expected_sid}, "
                f"got {DHAN_SEED_SECURITY_IDS.get((symbol, 'IDX'))!r}"
            )
            assert DHAN_SEED_SECURITY_IDS[(symbol, "IDX_I")] == expected_sid, (
                f"{symbol} IDX_I: expected {expected_sid}, "
                f"got {DHAN_SEED_SECURITY_IDS.get((symbol, 'IDX_I'))!r}"
            )

    def test_bse_equity_seed_table(self):
        for symbol, expected_sid in EXPECTED_BSE_EQUITY.items():
            assert DHAN_SEED_SECURITY_IDS[(symbol, "BSE")] == expected_sid, (
                f"{symbol} BSE: expected {expected_sid}, "
                f"got {DHAN_SEED_SECURITY_IDS.get((symbol, 'BSE'))!r}"
            )

    def test_no_legacy_drift_in_seed_table(self):
        """None of the *known wrong* historical IDs may be present."""
        # These were the values previously hard-coded in the legacy seed table
        # before the re-audit.  Pin them as forbidden so a regression is caught.
        legacy_wrong = {
            ("SBIN", "NSE"): "11536",  # this was actually TCS
            ("INFY", "NSE"): "10906",
            ("HDFCBANK", "NSE"): "10209",
            ("FINNIFTY", "IDX"): "45",
            ("FINNIFTY", "IDX_I"): "45",
            ("NIFTYNXT50", "IDX"): "299",
            ("NIFTYNXT50", "IDX_I"): "299",
        }
        for key, bad_value in legacy_wrong.items():
            assert DHAN_SEED_SECURITY_IDS.get(key) != bad_value, (
                f"Legacy wrong value {bad_value!r} reappeared for {key}"
            )

    def test_all_security_ids_are_strings_of_digits(self):
        for (sym, exch), sid in DHAN_SEED_SECURITY_IDS.items():
            assert isinstance(sid, str), f"{sym}/{exch}: sid is not a string"
            assert sid.isdigit(), f"{sym}/{exch}: sid {sid!r} is not all digits"

    def test_no_duplicate_security_ids_for_same_exchange(self):
        """Two different symbols on the same exchange cannot share an SID."""
        from collections import defaultdict

        bucket: dict = defaultdict(list)
        for (sym, exch), sid in DHAN_SEED_SECURITY_IDS.items():
            bucket[(exch, sid)].append(sym)
        for (exch, sid), symbols in bucket.items():
            assert len(symbols) == 1, f"Duplicate securityId {sid!r} on {exch}: {symbols!r}"


class TestInstrumentRegistryMatchesSeed:
    """The InstrumentRegistry must agree with the verified seed table."""

    def test_equity_sids_match(self):
        reg = InstrumentRegistry()
        for symbol, expected_sid in EXPECTED_NSE_EQUITY.items():
            assert reg.broker_identifier(symbol, "NSE") == expected_sid, (
                f"Registry has wrong SID for {symbol}/NSE"
            )

    def test_index_sids_match(self):
        reg = InstrumentRegistry()
        for symbol, expected_sid in EXPECTED_NSE_INDICES.items():
            assert reg.broker_identifier(symbol, "IDX") == expected_sid, (
                f"Registry has wrong SID for {symbol}/IDX"
            )
            assert reg.broker_identifier(symbol, "IDX_I") == expected_sid, (
                f"Registry has wrong SID for {symbol}/IDX_I"
            )

    def test_bse_equity_sids_match(self):
        reg = InstrumentRegistry()
        for symbol, expected_sid in EXPECTED_BSE_EQUITY.items():
            assert reg.broker_identifier(symbol, "BSE") == expected_sid, (
                f"Registry has wrong SID for {symbol}/BSE"
            )

    def test_indices_have_index_asset_class(self):
        reg = InstrumentRegistry()
        for symbol in EXPECTED_NSE_INDICES:
            instr = reg.resolve(symbol, "IDX")
            assert instr is not None
            assert instr.asset_class == InstrumentType.INDEX, (
                f"{symbol} should be classified as INDEX"
            )

    def test_equities_have_equity_asset_class(self):
        reg = InstrumentRegistry()
        for symbol in EXPECTED_NSE_EQUITY:
            instr = reg.resolve(symbol, "NSE")
            assert instr is not None
            assert instr.asset_class == InstrumentType.EQUITY, (
                f"{symbol} should be classified as EQUITY"
            )

    def test_canonical_symbol_lookup_via_sid(self):
        """broker_identifier -> canonical symbol round-trip works."""
        reg = InstrumentRegistry()
        assert reg.canonical_symbol(SBIN_NSE_SID, "NSE") == "SBIN"
        assert reg.canonical_symbol(INFY_NSE_SID, "NSE") == "INFY"
        assert reg.canonical_symbol(HDFCBANK_NSE_SID, "NSE") == "HDFCBANK"
        assert reg.canonical_symbol(RELIANCE_NSE_SID, "NSE") == "RELIANCE"
        assert reg.canonical_symbol(TCS_NSE_SID, "NSE") == "TCS"
        assert reg.canonical_symbol(NIFTY_IDX_SID, "IDX") == "NIFTY"
        assert reg.canonical_symbol(BANKNIFTY_IDX_SID, "IDX") == "BANKNIFTY"
        assert reg.canonical_symbol(NIFTYNXT50_IDX_SID, "IDX") == "NIFTYNXT50"

    def test_unknown_symbol_raises(self):
        reg = InstrumentRegistry()
        with pytest.raises(KeyError):
            reg.broker_identifier("DOES_NOT_EXIST", "NSE")


class TestDhanInstrumentResolverMatchesSeed:
    """The legacy DhanInstrumentResolver seed table must also agree."""

    def test_seed_table_keys_match_master(self):
        """Every entry in the verified seed must also be in the resolver seed."""
        resolver_seeds = DhanInstrumentResolver._SEED_SECURITY_IDS
        for key, sid in DHAN_SEED_SECURITY_IDS.items():
            assert resolver_seeds.get(key) == sid, (
                f"DhanInstrumentResolver seed disagrees at {key}: "
                f"expected {sid}, got {resolver_seeds.get(key)!r}"
            )

    def test_resolver_resolves_well_known_equity(self):
        r = DhanInstrumentResolver()
        for symbol, expected_sid in EXPECTED_NSE_EQUITY.items():
            assert r.resolve_security_id(symbol, "NSE") == expected_sid, (
                f"Resolver returned wrong SID for {symbol}/NSE"
            )

    def test_resolver_resolves_well_known_index(self):
        r = DhanInstrumentResolver()
        for symbol, expected_sid in EXPECTED_NSE_INDICES.items():
            assert r.resolve_security_id(symbol, "IDX") == expected_sid, (
                f"Resolver returned wrong SID for {symbol}/IDX"
            )
            assert r.resolve_security_id(symbol, "IDX_I") == expected_sid, (
                f"Resolver returned wrong SID for {symbol}/IDX_I"
            )

    def test_resolver_resolves_via_instrument_registry_fallback(self):
        """Even if the catalog is empty, the resolver must use the registry."""
        r = DhanInstrumentResolver()
        # With an empty catalog, super().resolve_security_id should fall back to
        # the InstrumentRegistry.  Since both seeds agree on the verified IDs,
        # this round-trip must succeed with the right SID.
        for symbol, expected_sid in EXPECTED_NSE_EQUITY.items():
            actual = r.resolve_security_id(symbol, "NSE")
            assert actual == expected_sid, (
                f"Catalog-empty resolver returned {actual!r} for {symbol}/NSE, "
                f"expected {expected_sid!r}"
            )

    def test_resolver_raises_for_unknown_symbol(self):
        r = DhanInstrumentResolver()
        with pytest.raises(ValueError):
            r.resolve_security_id("NOTREAL", "NSE")


class TestResolverAndRegistryAgreement:
    """Both code paths must agree on the same symbol/exchange."""

    @pytest.mark.parametrize("symbol,exchange", [(sym, "NSE") for sym in EXPECTED_NSE_EQUITY])
    def test_nse(self, symbol, exchange):
        reg = InstrumentRegistry().broker_identifier(symbol, exchange)
        res = DhanInstrumentResolver().resolve_security_id(symbol, exchange)
        assert reg == res, f"{symbol}/{exchange}: registry={reg!r} resolver={res!r}"

    @pytest.mark.parametrize("symbol,exchange", [(sym, "IDX") for sym in EXPECTED_NSE_INDICES])
    def test_idx(self, symbol, exchange):
        reg = InstrumentRegistry().broker_identifier(symbol, exchange)
        res = DhanInstrumentResolver().resolve_security_id(symbol, exchange)
        assert reg == res, f"{symbol}/{exchange}: registry={reg!r} resolver={res!r}"

    @pytest.mark.parametrize("symbol,exchange", [(sym, "IDX_I") for sym in EXPECTED_NSE_INDICES])
    def test_idx_i(self, symbol, exchange):
        reg = InstrumentRegistry().broker_identifier(symbol, exchange)
        res = DhanInstrumentResolver().resolve_security_id(symbol, exchange)
        assert reg == res, f"{symbol}/{exchange}: registry={reg!r} resolver={res!r}"

    @pytest.mark.parametrize("symbol,exchange", [(sym, "BSE") for sym in EXPECTED_BSE_EQUITY])
    def test_bse(self, symbol, exchange):
        reg = InstrumentRegistry().broker_identifier(symbol, exchange)
        res = DhanInstrumentResolver().resolve_security_id(symbol, exchange)
        assert reg == res, f"{symbol}/{exchange}: registry={reg!r} resolver={res!r}"


class TestSegmentMapperIntegrity:
    """Cross-check that the Dhan segment mapper recognises the seed exchanges."""

    def test_id_seg_lookup(self):
        reg = InstrumentRegistry()
        for _symbol in EXPECTED_NSE_INDICES:
            seg = reg.exchange_segment("IDX")
            assert seg == ExchangeSegment.IDX_I

    def test_nse_seg_lookup(self):
        reg = InstrumentRegistry()
        for _symbol in EXPECTED_NSE_EQUITY:
            seg = reg.exchange_segment("NSE")
            assert seg == ExchangeSegment.NSE


class TestCommonRegressions:
    """Pin the actual wrong-vs-right values for stocks the legacy code got wrong."""

    def test_sbin_is_not_11536(self):
        """SBIN's securityId must NOT be 11536 (that's TCS)."""
        assert InstrumentRegistry().broker_identifier("SBIN", "NSE") != "11536"
        assert DhanInstrumentResolver().resolve_security_id("SBIN", "NSE") != "11536"
        assert InstrumentRegistry().broker_identifier("SBIN", "NSE") == SBIN_NSE_SID

    def test_infy_is_not_10906(self):
        assert InstrumentRegistry().broker_identifier("INFY", "NSE") != "10906"
        assert DhanInstrumentResolver().resolve_security_id("INFY", "NSE") != "10906"
        assert InstrumentRegistry().broker_identifier("INFY", "NSE") == INFY_NSE_SID

    def test_hdfcbank_is_not_10209(self):
        assert InstrumentRegistry().broker_identifier("HDFCBANK", "NSE") != "10209"
        assert DhanInstrumentResolver().resolve_security_id("HDFCBANK", "NSE") != "10209"
        assert InstrumentRegistry().broker_identifier("HDFCBANK", "NSE") == HDFCBANK_NSE_SID

    def test_finnifty_is_not_45(self):
        assert InstrumentRegistry().broker_identifier("FINNIFTY", "IDX") != "45"
        assert DhanInstrumentResolver().resolve_security_id("FINNIFTY", "IDX") != "45"
        assert InstrumentRegistry().broker_identifier("FINNIFTY", "IDX") == FINNIFTY_IDX_SID

    def test_niftynxt50_is_not_299(self):
        assert InstrumentRegistry().broker_identifier("NIFTYNXT50", "IDX") != "299"
        assert DhanInstrumentResolver().resolve_security_id("NIFTYNXT50", "IDX") != "299"
        assert InstrumentRegistry().broker_identifier("NIFTYNXT50", "IDX") == NIFTYNXT50_IDX_SID
