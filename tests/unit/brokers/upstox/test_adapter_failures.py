"""Failure-path tests for Upstox adapters/clients (TEST-01, TEST-02).

These tests verify that adapters and clients gracefully handle:
- Network failures (connection errors, timeouts)
- API errors (4xx, 5xx responses)
- Invalid responses (malformed JSON, missing fields)
- Empty responses

All tests use mocks to simulate failure scenarios without requiring
live API connections.
"""

from __future__ import annotations

from unittest.mock import Mock

import pytest

from brokers.upstox.auth.exceptions import UpstoxApiError
from brokers.upstox.ipo.adapter import UpstoxIpoAdapter
from brokers.upstox.ipo.client import UpstoxIpoClient


class TestIpoAdapterFailures:
    """Verify IPO adapter handles failures gracefully."""

    def test_get_ipos_network_error(self):
        """Network error should raise UpstoxApiError."""
        mock_client = Mock()
        mock_client.get_ipo_data.side_effect = ConnectionError("Network unreachable")

        adapter = UpstoxIpoAdapter(mock_client)

        with pytest.raises((ConnectionError, UpstoxApiError)):
            adapter.get_ipos()

    def test_get_ipos_api_error(self):
        """API error (500) should raise UpstoxApiError."""
        mock_client = Mock()
        mock_client.get_ipo_data.side_effect = UpstoxApiError(
            "Internal server error", status_code=500
        )

        adapter = UpstoxIpoAdapter(mock_client)

        with pytest.raises(UpstoxApiError) as exc_info:
            adapter.get_ipos()

        assert exc_info.value.status_code == 500

    def test_get_ipos_empty_response(self):
        """Empty list should be returned as-is."""
        mock_client = Mock()
        mock_client.get_ipo_data.return_value = []

        adapter = UpstoxIpoAdapter(mock_client)
        result = adapter.get_ipos()

        assert result == []

    def test_get_ipos_malformed_response(self):
        """Malformed response should be passed through (adapter is thin wrapper)."""
        mock_client = Mock()
        mock_client.get_ipo_data.return_value = [{"invalid": "data"}]

        adapter = UpstoxIpoAdapter(mock_client)
        result = adapter.get_ipos()

        assert len(result) == 1
        assert result[0] == {"invalid": "data"}


class TestAdapterErrorPropagation:
    """Verify errors propagate correctly through adapter chain."""

    def test_ipo_client_http_error(self):
        """IPO client should raise UpstoxApiError on HTTP error."""
        mock_http = Mock()
        mock_http.get_json.side_effect = UpstoxApiError("Rate limit exceeded", status_code=429)

        client = UpstoxIpoClient(mock_http, Mock())

        with pytest.raises(UpstoxApiError) as exc_info:
            client.get_ipo_data()

        assert exc_info.value.status_code == 429
