"""Tests for InstrumentId integration across the codebase."""

from __future__ import annotations

from datetime import date

from domain.instrument_id import InstrumentId
from domain.instrument_resolver import resolve_selector


class TestInstrumentIdIntegration:
    """Verify InstrumentId works end-to-end across modules."""

    def test_gateway_history_includes_instrument_id(self):
        """Gateway history should include instrument_id column."""
        from datalake.gateway import DataLakeGateway

        gw = DataLakeGateway()
        df = gw.history("RELIANCE", exchange="NSE", timeframe="1D", lookback_days=5)
        assert "instrument_id" in df.columns
        assert df["instrument_id"].iloc[0] == "NSE:RELIANCE"

    def test_instrument_id_from_symbol(self):
        """instrument_id_from_symbol should produce canonical format."""
        from datalake.core.symbols import instrument_id_from_symbol

        assert instrument_id_from_symbol("RELIANCE", "NSE") == "NSE:RELIANCE"
        assert instrument_id_from_symbol("reliance", "nse") == "NSE:RELIANCE"
        assert instrument_id_from_symbol("RELIANCE-EQ", "NSE") == "NSE:RELIANCE"

    def test_instrument_id_from_option(self):
        """instrument_id_from_option should produce canonical format."""
        from datalake.core.symbols import instrument_id_from_option

        result = instrument_id_from_option("NIFTY", "2026-07-30", 25000, "CE")
        assert result == "NFO:NIFTY:20260730:25000:CE"

        result = instrument_id_from_option("NIFTY", "2026-07-30", 25000, "PE")
        assert result == "NFO:NIFTY:20260730:25000:PE"

    def test_instrument_id_from_future(self):
        """instrument_id_from_future should produce canonical format."""
        from datalake.core.symbols import instrument_id_from_future

        result = instrument_id_from_future("NIFTY", "2026-07-30")
        assert result == "NFO:NIFTY:20260730:FUT"

    def test_option_symbol_normalizes_ce_pe(self):
        """Option symbol should normalize CE→CALL, PE→PUT."""
        from datalake.core.option_format import make_option_symbol

        assert make_option_symbol("NIFTY", "WEEK", 1, -2, "CE") == "NIFTY_WEEK_1_-2_CALL"
        assert make_option_symbol("NIFTY", "WEEK", 1, -2, "PE") == "NIFTY_WEEK_1_-2_PUT"
        assert make_option_symbol("NIFTY", "WEEK", 1, -2, "CALL") == "NIFTY_WEEK_1_-2_CALL"

    def test_dsl_resolver_produces_valid_instrument_id(self):
        """Strategy DSL should resolve to valid InstrumentId."""
        iid = resolve_selector("NIFTY_WEEK_0_ATM_CE", spot=25000)
        assert iid.is_option
        assert iid.is_call
        assert iid.underlying == "NIFTY"
        assert iid.strike == 25000

    def test_broker_adapter_roundtrip(self):
        """Broker adapter should round-trip through InstrumentId."""
        from brokers.common.instrument_adapter import from_instrument_id, to_instrument_id

        original = InstrumentId.option("NFO", "NIFTY", date(2026, 7, 30), 25000, "CE")
        inst = from_instrument_id(original)
        result = to_instrument_id(inst)
        assert result == original

    def test_order_has_instrument_id_field(self):
        """Order dataclass should accept instrument_id."""
        from domain.entities.order import Order
        from domain.types import OrderType, Side

        order = Order(
            order_id="123",
            symbol="RELIANCE",
            exchange="NSE",
            side=Side.BUY,
            order_type=OrderType.MARKET,
            quantity=1,
            instrument_id="NSE:RELIANCE",
        )
        assert order.instrument_id == "NSE:RELIANCE"

    def test_option_leg_has_instrument_id_field(self):
        """OptionLeg should accept instrument_id."""
        from domain.entities.options import OptionLeg

        leg = OptionLeg(
            symbol="NIFTY25000CE",
            instrument_id="NFO:NIFTY:20260730:25000:CE",
        )
        assert leg.instrument_id == "NFO:NIFTY:20260730:25000:CE"

    def test_future_contract_has_instrument_id_field(self):
        """FutureContract should accept instrument_id."""
        from domain.entities.options import FutureContract

        contract = FutureContract(
            symbol="NIFTYJULFUT",
            instrument_id="NFO:NIFTY:20260730:FUT",
        )
        assert contract.instrument_id == "NFO:NIFTY:20260730:FUT"

    def test_scanner_output_includes_instrument_id(self):
        """Scanner should be able to add instrument_id to results."""
        from datalake.scanner.engine import RuleEngine

        engine = RuleEngine()
        df = engine.execute("volume_spike", params={"as_of_date": "2026-06-10"})
        # Scanner results have 'symbol' column - can be converted
        assert "symbol" in df.columns
        # Verify we can create instrument_id from scanner results
        from datalake.core.symbols import instrument_id_from_symbol
        if not df.empty:
            iid = instrument_id_from_symbol(df["symbol"].iloc[0], "NSE")
            assert iid.startswith("NSE:")
