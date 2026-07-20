"""Unit tests for interface.ui.commands._broker helpers."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from interface.ui.commands._broker import broker_id_from


@pytest.mark.unit
def test_broker_id_from_defaults_to_paper() -> None:
    assert broker_id_from(None, default="paper") == "paper"


@pytest.mark.unit
def test_broker_id_from_uses_service_name() -> None:
    service = type("S", (), {"active_broker_name": "dhan"})()
    assert broker_id_from(service, default="paper") == "dhan"
