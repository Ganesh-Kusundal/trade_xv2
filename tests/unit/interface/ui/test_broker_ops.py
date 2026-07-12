"""Unit tests for interface.ui.services.broker_ops."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from interface.ui.services.broker_ops import broker_id_from, fetch_quote, verify_broker


@pytest.mark.unit
def test_broker_id_from_defaults_to_paper() -> None:
    assert broker_id_from(None, default="paper") == "paper"


@pytest.mark.unit
def test_fetch_quote_delegates_to_get_quote() -> None:
    sentinel = object()
    with patch("interface.ui.services.broker_ops.get_quote", return_value=sentinel) as mock:
        result = fetch_quote(None, "RELIANCE", default="paper", exchange="NSE")
    assert result is sentinel
    mock.assert_called_once_with("paper", "RELIANCE", exchange="NSE")


@pytest.mark.unit
def test_verify_broker_paper_passes() -> None:
    report = verify_broker(None, default="paper")
    assert report.passed, report.to_dict()
