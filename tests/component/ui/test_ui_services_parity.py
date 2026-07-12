"""Parity between brokers.services and UI broker_ops adapter."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from interface.ui.services.broker_ops import fetch_quote


@pytest.mark.unit
def test_ui_services_parity_delegates_to_services() -> None:
    """fetch_quote must call brokers.services.get_quote with resolved broker id."""
    with patch("interface.ui.services.broker_ops.get_quote") as mock:
        mock.return_value = {"ltp": 1}
        out = fetch_quote(None, "RELIANCE", default="paper")
    assert out == {"ltp": 1}
    mock.assert_called_once()
    assert mock.call_args.args[0] == "paper"
    assert mock.call_args.args[1] == "RELIANCE"
