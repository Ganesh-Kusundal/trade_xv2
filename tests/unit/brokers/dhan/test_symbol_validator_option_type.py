"""Regression tests for F&O option-type validation.

Guards the bug where ``_validate_fo`` compared the instrument's option type
as ``"CALL"/"PUT"`` against the parsed ``"CE"/"PE"`` code, so every valid
option symbol was rejected as EXPIRED/INVALID.
"""

from __future__ import annotations

from brokers.providers.dhan.symbol_validator import DhanSymbolValidator


def test_validate_ce_option_resolves_to_call_contract(resolver):
    validator = DhanSymbolValidator(resolver)
    result = validator.validate("NIFTY 26 JUN 25000 CE")
    assert result["status"] == "VALID"
    assert result["securityId"] == "55000"
    assert result["optionType"] == "CE"


def test_validate_pe_option_resolves_to_put_contract(resolver):
    validator = DhanSymbolValidator(resolver)
    result = validator.validate("NIFTY 26 JUN 25000 PE")
    assert result["status"] == "VALID"
    assert result["securityId"] == "55001"
    assert result["optionType"] == "PE"


def test_validate_ce_and_pe_do_not_cross_match(resolver):
    """A CE query must not resolve to the PE security id (and vice versa)."""
    validator = DhanSymbolValidator(resolver)
    ce = validator.validate("NIFTY 26 JUN 25000 CE")
    pe = validator.validate("NIFTY 26 JUN 25000 PE")
    assert ce["securityId"] != pe["securityId"]
