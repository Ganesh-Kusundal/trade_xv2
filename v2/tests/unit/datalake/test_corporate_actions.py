"""CorporateActionStore adjust_price for stock splits."""

from __future__ import annotations

from datalake.corporate_actions import CorporateActionStore


def test_adjust_price_2_for_1_split() -> None:
    store = CorporateActionStore()
    # 2:1 split → each share becomes 2; price halves
    assert store.adjust_price(100.0, ratio=2.0) == 50.0


def test_adjust_price_identity_when_ratio_one() -> None:
    store = CorporateActionStore()
    assert store.adjust_price(250.5, ratio=1.0) == 250.5


def test_record_split_and_adjust() -> None:
    store = CorporateActionStore()
    store.record_split("RELIANCE", ratio=2.0)
    assert store.adjust_price(200.0, symbol="RELIANCE") == 100.0
