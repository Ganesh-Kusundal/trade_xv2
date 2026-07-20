"""Cross-cutting system invariants (money path, isolation)."""

from __future__ import annotations

import pytest

from brokers.dhan.exceptions import DhanIdentityError
from brokers.dhan.identity import DhanInstrumentRef
from brokers.dhan.resilience.invariants import (
    VALID_SEGMENTS,
    assert_dhan_identity,
    assert_valid_security_id,
)

# ── assert_dhan_identity Tests ────────────────────────────────────────────


class TestAssertDhanIdentity:
    """Test assert_dhan_identity() function."""

    def test_valid_ref_passes(self):
        """Valid DhanInstrumentRef should pass without error."""
        ref = DhanInstrumentRef(
            security_id="11536",
            exchange_segment="NSE_EQ",
            symbol="RELIANCE",
            exchange="NSE",
        )
        # Should not raise
        assert_dhan_identity(ref)

    def test_valid_ref_with_synthetic_index_passes(self):
        """Valid ref with synthetic index flag should pass."""
        ref = DhanInstrumentRef(
            security_id="13",
            exchange_segment="IDX_I",
            symbol="NIFTY",
            exchange="INDEX",
            is_synthetic_index=True,
        )
        # Should not raise
        assert_dhan_identity(ref)

    def test_all_valid_segments_pass(self):
        """All valid Dhan segments should pass validation."""
        for segment in VALID_SEGMENTS:
            ref = DhanInstrumentRef(
                security_id="11536",
                exchange_segment=segment,
                symbol="RELIANCE",
                exchange="NSE",
            )
            # Should not raise
            assert_dhan_identity(ref)

    def test_rejects_none(self):
        """None should be rejected."""
        with pytest.raises(DhanIdentityError, match="Not a DhanInstrumentRef"):
            assert_dhan_identity(None)

    def test_rejects_string(self):
        """String should be rejected."""
        with pytest.raises(DhanIdentityError, match="Not a DhanInstrumentRef"):
            assert_dhan_identity("not_a_ref")

    def test_rejects_dict(self):
        """Dict should be rejected."""
        with pytest.raises(DhanIdentityError, match="Not a DhanInstrumentRef"):
            assert_dhan_identity({"security_id": "11536"})

    def test_rejects_object_without_security_id(self):
        """Object without security_id attribute should be rejected."""

        class FakeRef:
            exchange_segment = "NSE_EQ"

        with pytest.raises(DhanIdentityError, match="Not a DhanInstrumentRef"):
            assert_dhan_identity(FakeRef())

    def test_rejects_object_without_exchange_segment(self):
        """Object without exchange_segment attribute should be rejected."""

        class FakeRef:
            security_id = "11536"

        with pytest.raises(DhanIdentityError, match="Not a DhanInstrumentRef"):
            assert_dhan_identity(FakeRef())

    def test_rejects_empty_security_id(self):
        """Empty security_id should be rejected during construction."""
        with pytest.raises(DhanIdentityError, match="Invalid security_id"):
            DhanInstrumentRef(
                security_id="",
                exchange_segment="NSE_EQ",
                symbol="RELIANCE",
                exchange="NSE",
            )

    def test_rejects_non_digit_security_id(self):
        """Non-digit security_id should be rejected during construction."""
        with pytest.raises(DhanIdentityError, match="Invalid security_id"):
            DhanInstrumentRef(
                security_id="abc123",
                exchange_segment="NSE_EQ",
                symbol="RELIANCE",
                exchange="NSE",
            )

    def test_rejects_negative_security_id(self):
        """Negative security_id should be rejected during construction."""
        with pytest.raises(DhanIdentityError, match="Invalid security_id"):
            DhanInstrumentRef(
                security_id="-1",
                exchange_segment="NSE_EQ",
                symbol="RELIANCE",
                exchange="NSE",
            )

    def test_rejects_zero_security_id(self):
        """Zero security_id should be rejected during construction."""
        with pytest.raises(DhanIdentityError, match="Invalid security_id"):
            DhanInstrumentRef(
                security_id="0",
                exchange_segment="NSE_EQ",
                symbol="RELIANCE",
                exchange="NSE",
            )

    def test_rejects_invalid_exchange_segment(self):
        """Invalid exchange_segment should be rejected during construction."""
        with pytest.raises(DhanIdentityError, match="Invalid exchange_segment"):
            DhanInstrumentRef(
                security_id="11536",
                exchange_segment="INVALID",
                symbol="RELIANCE",
                exchange="NSE",
            )

    def test_rejects_upstox_segment(self):
        """Upstox segment should be rejected during construction (not a Dhan segment)."""
        with pytest.raises(DhanIdentityError, match="Invalid exchange_segment"):
            DhanInstrumentRef(
                security_id="11536",
                exchange_segment="NSE_INDEX",  # Upstox-style segment
                symbol="NIFTY",
                exchange="INDEX",
            )


# ── assert_valid_security_id Tests ────────────────────────────────────────


class TestAssertValidSecurityId:
    """Test assert_valid_security_id() function."""

    def test_valid_numeric_string_passes(self):
        """Valid numeric string should pass."""
        # Should not raise
        assert_valid_security_id("11536")

    def test_valid_large_number_passes(self):
        """Large numeric string should pass."""
        # Should not raise
        assert_valid_security_id("999999999")

    def test_valid_single_digit_passes(self):
        """Single digit should pass."""
        # Should not raise
        assert_valid_security_id("1")

    def test_rejects_empty_string(self):
        """Empty string should be rejected."""
        with pytest.raises(DhanIdentityError, match="Invalid security_id"):
            assert_valid_security_id("")

    def test_rejects_none_type(self):
        """None should be rejected (type error or identity error)."""
        with pytest.raises((TypeError, DhanIdentityError)):
            assert_valid_security_id(None)  # type: ignore[arg-type]

    def test_rejects_non_digit_string(self):
        """Non-digit string should be rejected."""
        with pytest.raises(DhanIdentityError, match="Invalid security_id"):
            assert_valid_security_id("abc123")

    def test_rejects_mixed_string(self):
        """Mixed digit/non-digit string should be rejected."""
        with pytest.raises(DhanIdentityError, match="Invalid security_id"):
            assert_valid_security_id("123abc")

    def test_rejects_negative_number(self):
        """Negative number string should be rejected."""
        with pytest.raises(DhanIdentityError, match="Invalid security_id"):
            assert_valid_security_id("-123")

    def test_rejects_zero(self):
        """Zero should be rejected."""
        with pytest.raises(DhanIdentityError, match="Invalid security_id"):
            assert_valid_security_id("0")

    def test_rejects_float_string(self):
        """Float string should be rejected."""
        with pytest.raises(DhanIdentityError, match="Invalid security_id"):
            assert_valid_security_id("123.45")

    def test_rejects_whitespace(self):
        """String with whitespace should be rejected."""
        with pytest.raises(DhanIdentityError, match="Invalid security_id"):
            assert_valid_security_id(" 11536 ")

    def test_rejects_leading_zeros_is_ok(self):
        """Leading zeros should be accepted (still a valid digit string)."""
        # Should not raise - "00123" is still digits
        assert_valid_security_id("00123")
