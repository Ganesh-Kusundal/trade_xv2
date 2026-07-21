"""Tests for Dhan identity provider — DhanInstrumentRef and DhanIdentityProvider.

Verifies:
- DhanInstrumentRef immutability and validation
- DhanIdentityProvider.resolve_ref() for various instrument types
- Expected segment guard prevents index-vs-derivative misroutes
- to_payload_security_id() returns string type
"""

from __future__ import annotations

from dataclasses import FrozenInstanceError
from decimal import Decimal
from unittest.mock import Mock

import pytest

# Import directly from submodules to avoid circular import through __init__.py
from brokers.providers.dhan._dhan_types import DhanInstrument, Exchange, InstrumentType
from brokers.providers.dhan.exceptions import DhanIdentityError, InstrumentNotFoundError
from brokers.providers.dhan.identity import DhanIdentityProvider, DhanInstrumentRef
from brokers.providers.dhan.resolver import SymbolResolver
from brokers.providers.dhan.segments import EXCHANGE_TO_SEGMENT
from domain.entities.instrument_record import InstrumentRecord as DomainInstrument

# ── DhanInstrumentRef Tests ────────────────────────────────────────────────


class TestDhanInstrumentRef:
    """Test DhanInstrumentRef dataclass."""

    def test_create_valid_ref(self):
        """Valid reference should be created successfully."""
        ref = DhanInstrumentRef(
            security_id="11536",
            exchange_segment="NSE_EQ",
            symbol="RELIANCE",
            exchange="NSE",
        )
        assert ref.security_id == "11536"
        assert ref.exchange_segment == "NSE_EQ"
        assert ref.symbol == "RELIANCE"
        assert ref.exchange == "NSE"
        assert ref.is_synthetic_index is False

    def test_create_valid_ref_with_synthetic_index(self):
        """Reference with synthetic index flag."""
        ref = DhanInstrumentRef(
            security_id="13",
            exchange_segment="IDX_I",
            symbol="NIFTY",
            exchange="INDEX",
            is_synthetic_index=True,
        )
        assert ref.is_synthetic_index is True

    def test_ref_is_immutable(self):
        """DhanInstrumentRef should be frozen (immutable)."""
        ref = DhanInstrumentRef(
            security_id="11536",
            exchange_segment="NSE_EQ",
            symbol="RELIANCE",
            exchange="NSE",
        )
        with pytest.raises(FrozenInstanceError):
            ref.security_id = "99999"

    def test_invalid_security_id_empty(self):
        """Empty security_id should raise DhanIdentityError."""
        with pytest.raises(DhanIdentityError, match="Invalid security_id"):
            DhanInstrumentRef(
                security_id="",
                exchange_segment="NSE_EQ",
                symbol="RELIANCE",
                exchange="NSE",
            )

    def test_invalid_security_id_non_digit(self):
        """Non-digit security_id should raise DhanIdentityError."""
        with pytest.raises(DhanIdentityError, match="Invalid security_id"):
            DhanInstrumentRef(
                security_id="abc123",
                exchange_segment="NSE_EQ",
                symbol="RELIANCE",
                exchange="NSE",
            )

    def test_invalid_security_id_negative(self):
        """Negative security_id should raise DhanIdentityError."""
        with pytest.raises(DhanIdentityError, match="Invalid security_id"):
            DhanInstrumentRef(
                security_id="-1",
                exchange_segment="NSE_EQ",
                symbol="RELIANCE",
                exchange="NSE",
            )

    def test_invalid_security_id_zero(self):
        """Zero security_id should raise DhanIdentityError."""
        with pytest.raises(DhanIdentityError, match="Invalid security_id"):
            DhanInstrumentRef(
                security_id="0",
                exchange_segment="NSE_EQ",
                symbol="RELIANCE",
                exchange="NSE",
            )

    def test_invalid_exchange_segment(self):
        """Invalid exchange_segment should raise DhanIdentityError."""
        with pytest.raises(DhanIdentityError, match="Invalid exchange_segment"):
            DhanInstrumentRef(
                security_id="11536",
                exchange_segment="INVALID_SEGMENT",
                symbol="RELIANCE",
                exchange="NSE",
            )

    def test_valid_segments(self):
        """All valid Dhan segments should be accepted."""
        valid_segments = list(EXCHANGE_TO_SEGMENT.values())
        for segment in valid_segments:
            ref = DhanInstrumentRef(
                security_id="11536",
                exchange_segment=segment,
                symbol="RELIANCE",
                exchange="NSE",
            )
            assert ref.exchange_segment == segment


# ── DhanIdentityProvider Tests ────────────────────────────────────────────


class TestDhanIdentityProvider:
    """Test DhanIdentityProvider.resolve_ref()."""

    def _create_instrument(
        self,
        symbol: str,
        exchange: Exchange,
        security_id: str,
        instrument_type: InstrumentType,
    ) -> DhanInstrument:
        """Helper to create a DhanInstrument using composition."""
        domain_inst = DomainInstrument(
            symbol=symbol,
            exchange=exchange.value,
            security_id=security_id,
            instrument_type=instrument_type.value,
            lot_size=1,
            tick_size=Decimal("0.05"),
        )
        return DhanInstrument(
            domain_instrument=domain_inst,
            exchange=exchange,
            instrument_type=instrument_type,
        )

    def _create_mock_resolver(self, instrument: DhanInstrument) -> SymbolResolver:
        """Create a mock resolver that returns the given instrument."""
        mock_resolver = Mock(spec=SymbolResolver)
        mock_resolver.resolve.return_value = instrument
        return mock_resolver

    def test_resolve_ref_equity(self):
        """Resolve equity instrument."""
        inst = self._create_instrument(
            symbol="RELIANCE",
            exchange=Exchange.NSE,
            security_id="11536",
            instrument_type=InstrumentType.EQUITY,
        )
        mock_resolver = self._create_mock_resolver(inst)
        identity = DhanIdentityProvider(mock_resolver)

        ref = identity.resolve_ref("RELIANCE", "NSE")

        assert ref.security_id == "11536"
        assert ref.exchange_segment == "NSE_EQ"
        assert ref.symbol == "RELIANCE"
        assert ref.exchange == "NSE"
        assert ref.is_synthetic_index is False

    def test_resolve_ref_option(self):
        """Resolve option instrument."""
        inst = self._create_instrument(
            symbol="NIFTY 26 JUN 25000 CE",
            exchange=Exchange.NFO,
            security_id="54321",
            instrument_type=InstrumentType.OPTION,
        )
        mock_resolver = self._create_mock_resolver(inst)
        identity = DhanIdentityProvider(mock_resolver)

        ref = identity.resolve_ref("NIFTY 26 JUN 25000 CE", "NFO")

        assert ref.security_id == "54321"
        assert ref.exchange_segment == "NSE_FNO"
        assert ref.is_synthetic_index is False

    def test_resolve_ref_future(self):
        """Resolve future instrument."""
        inst = self._create_instrument(
            symbol="RELIANCE 27 JUN 2025",
            exchange=Exchange.NFO,
            security_id="67890",
            instrument_type=InstrumentType.FUTURE,
        )
        mock_resolver = self._create_mock_resolver(inst)
        identity = DhanIdentityProvider(mock_resolver)

        ref = identity.resolve_ref("RELIANCE 27 JUN 2025", "NFO")

        assert ref.security_id == "67890"
        assert ref.exchange_segment == "NSE_FNO"

    def test_resolve_ref_index(self):
        """Resolve index instrument."""
        inst = self._create_instrument(
            symbol="NIFTY",
            exchange=Exchange.INDEX,
            security_id="13",
            instrument_type=InstrumentType.EQUITY,
        )
        mock_resolver = self._create_mock_resolver(inst)
        identity = DhanIdentityProvider(mock_resolver)

        ref = identity.resolve_ref("NIFTY", "INDEX")

        assert ref.security_id == "13"
        assert ref.exchange_segment == "IDX_I"

    def test_resolve_ref_mcx(self):
        """Resolve MCX commodity instrument."""
        inst = self._create_instrument(
            symbol="CRUDEOIL",
            exchange=Exchange.MCX,
            security_id="12345",
            instrument_type=InstrumentType.COMMODITY,
        )
        mock_resolver = self._create_mock_resolver(inst)
        identity = DhanIdentityProvider(mock_resolver)

        ref = identity.resolve_ref("CRUDEOIL", "MCX")

        assert ref.security_id == "12345"
        assert ref.exchange_segment == "MCX_COMM"

    def test_resolve_ref_not_found(self):
        """Resolver raises InstrumentNotFoundError if symbol not found."""
        mock_resolver = Mock(spec=SymbolResolver)
        mock_resolver.resolve.side_effect = InstrumentNotFoundError("Not found")
        identity = DhanIdentityProvider(mock_resolver)

        with pytest.raises(InstrumentNotFoundError):
            identity.resolve_ref("NONEXISTENT", "NSE")

    def test_expected_segment_guard_index_vs_derivative(self):
        """Should raise error when index resolved but derivative expected."""
        inst = self._create_instrument(
            symbol="NIFTY",
            exchange=Exchange.INDEX,
            security_id="13",
            instrument_type=InstrumentType.EQUITY,
        )
        mock_resolver = self._create_mock_resolver(inst)
        identity = DhanIdentityProvider(mock_resolver)

        with pytest.raises(DhanIdentityError, match="resolved to index"):
            identity.resolve_ref("NIFTY", "INDEX", expected_segment="NSE_FNO")

    def test_expected_segment_guard_all_derivative_segments(self):
        """Should raise error for all derivative segments."""
        inst = self._create_instrument(
            symbol="NIFTY",
            exchange=Exchange.INDEX,
            security_id="13",
            instrument_type=InstrumentType.EQUITY,
        )
        mock_resolver = self._create_mock_resolver(inst)
        identity = DhanIdentityProvider(mock_resolver)

        derivative_segments = ["NSE_FNO", "BSE_FNO", "MCX_COMM", "NSE_CURRENCY", "BSE_CURRENCY"]
        for segment in derivative_segments:
            with pytest.raises(DhanIdentityError, match="resolved to index"):
                identity.resolve_ref("NIFTY", "INDEX", expected_segment=segment)

    def test_expected_segment_none_allows_index(self):
        """Should allow index resolution when expected_segment is None."""
        inst = self._create_instrument(
            symbol="NIFTY",
            exchange=Exchange.INDEX,
            security_id="13",
            instrument_type=InstrumentType.EQUITY,
        )
        mock_resolver = self._create_mock_resolver(inst)
        identity = DhanIdentityProvider(mock_resolver)

        ref = identity.resolve_ref("NIFTY", "INDEX", expected_segment=None)
        assert ref.security_id == "13"
        assert ref.exchange_segment == "IDX_I"

    def test_expected_segment_allows_index_for_index_segment(self):
        """Should allow index resolution when expected_segment is IDX_I."""
        inst = self._create_instrument(
            symbol="NIFTY",
            exchange=Exchange.INDEX,
            security_id="13",
            instrument_type=InstrumentType.EQUITY,
        )
        mock_resolver = self._create_mock_resolver(inst)
        identity = DhanIdentityProvider(mock_resolver)

        ref = identity.resolve_ref("NIFTY", "INDEX", expected_segment="IDX_I")
        assert ref.exchange_segment == "IDX_I"

    def test_security_id_is_string(self):
        """security_id in ref should always be string type."""
        inst = self._create_instrument(
            symbol="RELIANCE",
            exchange=Exchange.NSE,
            security_id="11536",  # String in DhanInstrument
            instrument_type=InstrumentType.EQUITY,
        )
        mock_resolver = self._create_mock_resolver(inst)
        identity = DhanIdentityProvider(mock_resolver)

        ref = identity.resolve_ref("RELIANCE", "NSE")
        assert isinstance(ref.security_id, str)
        assert ref.security_id == "11536"


# ── to_payload_security_id Tests ──────────────────────────────────────────


class TestToPayloadSecurityId:
    """Test DhanIdentityProvider.to_payload_security_id()."""

    def test_returns_string(self):
        """Should return string type."""
        ref = DhanInstrumentRef(
            security_id="11536",
            exchange_segment="NSE_EQ",
            symbol="RELIANCE",
            exchange="NSE",
        )
        result = DhanIdentityProvider.to_payload_security_id(ref)
        assert isinstance(result, str)
        assert result == "11536"

    def test_handles_numeric_string(self):
        """Should handle numeric string security_id."""
        ref = DhanInstrumentRef(
            security_id="54321",
            exchange_segment="NSE_FNO",
            symbol="NIFTY OPTION",
            exchange="NFO",
        )
        result = DhanIdentityProvider.to_payload_security_id(ref)
        assert result == "54321"
        assert isinstance(result, str)
