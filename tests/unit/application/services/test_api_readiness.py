"""API readiness gate evaluation (TRANS-P4-005)."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

from application.services.api_readiness import evaluate_api_readiness


def test_readiness_fails_without_event_bus_or_oms() -> None:
    container = SimpleNamespace(
        datalake_gateway=object(),
        view_manager=object(),
        data_catalog=object(),
        event_bus=None,
        trading_context=None,
        broker_service=None,
    )
    report = evaluate_api_readiness(container)
    assert report.ready is False
    ids = {c.id for c in report.checks}
    assert "event_bus" in ids
    assert "oms_context" in ids


def test_readiness_passes_with_wired_oms() -> None:
    tc = MagicMock()
    tc.event_bus = MagicMock()
    tc.health.return_value = {"reconciliation_ready": True}
    container = SimpleNamespace(
        datalake_gateway=object(),
        view_manager=object(),
        data_catalog=object(),
        event_bus=tc.event_bus,
        trading_context=tc,
        broker_service=SimpleNamespace(
            active_broker=None,
            live_actionable=False,
            _live_intent=False,
        ),
    )
    report = evaluate_api_readiness(container)
    assert report.ready is True


def test_readiness_fails_when_single_dependency_is_down() -> None:
    """DR-F2: a single dependency going down must flip /ready to not-ready.

    Isolates the datalake_gateway (the DB-backed dependency) being None while
    every other gate passes, and asserts the overall report is not ready and the
    datalake_gateway gate specifically failed. This is the contract the /ready
    endpoint enforces (503 when not ready).
    """
    tc = MagicMock()
    tc.event_bus = MagicMock()
    tc.health.return_value = {"reconciliation_ready": True}
    container = SimpleNamespace(
        datalake_gateway=None,  # DB dependency down
        view_manager=object(),
        data_catalog=object(),
        event_bus=tc.event_bus,
        trading_context=tc,
        broker_service=SimpleNamespace(
            active_broker=None,
            live_actionable=False,
            _live_intent=False,
        ),
    )
    report = evaluate_api_readiness(container)
    assert report.ready is False
    statuses = {c.id: c.status for c in report.checks}
    assert statuses["datalake_gateway"] == "failed"
    assert statuses["event_bus"] == "passed"
    assert statuses["oms_context"] == "passed"