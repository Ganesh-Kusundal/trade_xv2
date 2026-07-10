"""Tests for AccountAggregate (canonical: domain.aggregates)."""

from __future__ import annotations

from decimal import Decimal

from domain.aggregates import AccountAggregate
from domain.entities.account import Balance


def test_account_aggregate_identity():
    agg = AccountAggregate(account_id="acc1")
    assert agg.account_id == "acc1"


def test_account_aggregate_balance():
    bal = Balance(available_balance=Decimal("50000"))
    agg = AccountAggregate(account_id="acc1", balance=bal)
    assert agg.available_balance == Decimal("50000")
    assert agg.has_sufficient(Decimal("40000"))
    assert not agg.has_sufficient(Decimal("60000"))
