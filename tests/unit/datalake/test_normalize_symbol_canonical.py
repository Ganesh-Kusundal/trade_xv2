"""Phase 3 — domain and datalake agree on canonical normalize_symbol (F8)."""

from __future__ import annotations

from datalake.core.symbols import normalize_symbol as dl_normalize
from datalake.core.symbols import normalize_symbol_for_storage
from domain.symbols import normalize_symbol as domain_normalize


def test_canonical_normalize_symbol_agrees_on_reliance_eq() -> None:
    """Canonical function keeps suffix; domain and datalake must match."""
    raw = "RELIANCE-EQ"
    assert domain_normalize(raw) == "RELIANCE-EQ"
    assert dl_normalize(raw) == domain_normalize(raw)


def test_storage_helper_strips_exchange_suffix() -> None:
    assert normalize_symbol_for_storage("RELIANCE-EQ") == "RELIANCE"
    assert normalize_symbol_for_storage("  tcs-be  ") == "TCS"
