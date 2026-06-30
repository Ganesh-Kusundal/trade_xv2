"""Tests for api.routers.live.headers — provenance headers."""

from __future__ import annotations

from unittest.mock import MagicMock

from api.routers.live.headers import apply_live_headers


class TestApplyLiveHeaders:
    def test_sets_data_source(self):
        response = MagicMock()
        response.headers = {}
        apply_live_headers(response, "dhan")
        assert response.headers["X-Data-Source"] == "live_broker"

    def test_sets_broker_name(self):
        response = MagicMock()
        response.headers = {}
        apply_live_headers(response, "upstox")
        assert response.headers["X-Broker-Name"] == "upstox"

    def test_sets_both_headers(self):
        response = MagicMock()
        response.headers = {}
        apply_live_headers(response, "dhan")
        assert len(response.headers) == 2
