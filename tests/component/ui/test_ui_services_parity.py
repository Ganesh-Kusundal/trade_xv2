"""Parity between brokers.services and UI command broker helpers."""

from __future__ import annotations

import pytest

from interface.ui.commands._broker import broker_id_from


@pytest.mark.unit
def test_broker_id_from_resolves_for_cli() -> None:
    service = type("S", (), {"active_broker_name": "dhan"})()
    assert broker_id_from(service, default="paper") == "dhan"
