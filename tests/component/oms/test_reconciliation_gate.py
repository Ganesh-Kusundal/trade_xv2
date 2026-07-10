"""Tests for post-restart reconciliation order placement gate."""

from __future__ import annotations
from tests.conftest import build_test_trading_context

from application.oms.context import TradingContext


class _FakeReconciler:
    def reconcile(self, local_orders, local_positions):
        return type("Report", (), {"has_drift": False, "drift_items": []})()


def test_trading_context_reconciliation_ready_without_service() -> None:
    """Without a reconciliation service, reconciliation is immediately ready."""
    tc = build_test_trading_context(
        replay_events=False,
        enable_durable_orders=False,
    )
    assert tc.health()["reconciliation_ready"]


def test_tracking_context_default_reconciliation_state() -> None:
    """TradingContext exposes reconciliation_ready in health check."""
    tc = build_test_trading_context(
        replay_events=False,
        enable_durable_orders=False,
    )
    health = tc.health()
    assert "reconciliation_ready" in health
    assert isinstance(health["reconciliation_ready"], bool)
