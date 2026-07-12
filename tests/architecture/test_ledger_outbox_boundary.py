"""TRANS-P5-030 — ledger outbox record-then-submit boundary."""

from __future__ import annotations

import inspect

import pytest


@pytest.mark.architecture
def test_order_lifecycle_uses_ledger_outbox() -> None:
    from application.oms._internal import order_lifecycle

    lifecycle_src = inspect.getsource(order_lifecycle.OrderLifecycle.submit_to_broker)
    assert "persist_intent_then_submit" in lifecycle_src

    from application.oms import ledger_outbox

    outbox_src = inspect.getsource(ledger_outbox.persist_intent_then_submit)
    assert "record_intent" in outbox_src


@pytest.mark.architecture
def test_ledger_outbox_module_exists() -> None:
    from application.oms.ledger_outbox import persist_intent_then_submit

    assert callable(persist_intent_then_submit)