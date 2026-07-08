"""Tests for accounts sub-package re-export."""

from __future__ import annotations

from decimal import Decimal

from domain.accounts import AccountAggregate
from domain.entities.account import Balance


def test_import_from_accounts():
    assert AccountAggregate is not None


def test_accounts_aggregate_identity():
    agg = AccountAggregate(account_id="acc1")
    assert agg.account_id == "acc1"


def test_accounts_aggregate_balance():
    bal = Balance(available_balance=Decimal("50000"))
    agg = AccountAggregate(account_id="acc1", balance=bal)
    assert agg.available_balance == Decimal("50000")
    assert agg.has_sufficient(Decimal("40000"))
    assert not agg.has_sufficient(Decimal("60000"))
