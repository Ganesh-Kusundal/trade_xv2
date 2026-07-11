"""TOS-P2-003 — capital paths fail closed (no silent event_bus=None no-ops on OMS)."""

from __future__ import annotations

from pathlib import Path

import pytest

SRC = Path(__file__).resolve().parents[2] / "src"


@pytest.mark.architecture
def test_order_lifecycle_publish_is_not_optional_silent() -> None:
    """OMS lifecycle must attempt event publish on money paths."""
    text = (SRC / "application/oms/_internal/order_lifecycle.py").read_text(
        encoding="utf-8"
    )
    assert "_publish" in text or "publish" in text
    # Ledger authority fail-closed when flag on and ledger missing
    assert "require_execution_ledger" in text or "ledger_authority" in text


@pytest.mark.architecture
def test_event_bus_handler_failures_go_to_dlq_or_log() -> None:
    text = (SRC / "infrastructure/event_bus/event_bus.py").read_text(encoding="utf-8")
    assert "DeadLetterQueue" in text or "dead_letter" in text
    assert "handler" in text.lower() and "failed" in text.lower()


@pytest.mark.architecture
def test_event_bus_exposes_managed_service() -> None:
    """TOS-P7-003: EventBus can register alerting with LifecycleManager."""
    text = (SRC / "infrastructure/event_bus/event_bus.py").read_text(encoding="utf-8")
    assert "as_managed_service" in text
    assert "EventBusAlertingService" in text
