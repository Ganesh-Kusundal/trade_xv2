"""Backward-compat shim — invariants now live in ``brokers.dhan.resilience.invariants``."""
from brokers.dhan.resilience.invariants import (  # noqa: F401
    VALID_SEGMENTS,
    assert_dhan_identity,
    assert_dhan_payload,
    assert_dhan_segment,
    assert_valid_security_id,
)
