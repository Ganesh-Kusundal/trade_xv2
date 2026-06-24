"""Contract tests for extended /api/v1/live/* account routes."""

from __future__ import annotations

from fastapi.testclient import TestClient


def test_live_profile_headers(live_client: TestClient) -> None:
    resp = live_client.get("/api/v1/live/profile")
    assert resp.status_code == 200
    assert resp.headers.get("X-Data-Source") == "live_broker"
    assert resp.headers.get("X-Broker-Name") == "dhan"
    assert resp.json()["name"] == "stub"


def test_live_ledger(live_client: TestClient) -> None:
    resp = live_client.get(
        "/api/v1/live/ledger",
        params={"from_date": "2026-01-01", "to_date": "2026-01-31"},
    )
    assert resp.status_code == 200
    assert resp.headers.get("X-Data-Source") == "live_broker"
    assert resp.json() == []


def test_live_ip(live_client: TestClient) -> None:
    resp = live_client.get("/api/v1/live/ip")
    assert resp.status_code == 200
    assert resp.json()["ip"] == "127.0.0.1"
