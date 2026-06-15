"""Conditional alerts adapter."""

from __future__ import annotations

from brokers.dhan.http_client import DhanHttpClient
from brokers.dhan.resolver import SymbolResolver


class AlertsAdapter:
    def __init__(self, client: DhanHttpClient, resolver: SymbolResolver):
        self._client = client
        self._resolver = resolver

    def place(self, payload: dict) -> dict:
        return self._client.post("/alerts", json=payload)

    def get(self, alert_id: str) -> dict:
        return self._client.get(f"/alerts/{alert_id}")

    def list_all(self) -> list[dict]:
        data = self._client.get("/alerts")
        return data.get("data", []) if isinstance(data, dict) else []

    def delete(self, alert_id: str) -> bool:
        data = self._client.delete(f"/alerts/{alert_id}")
        return isinstance(data, dict)
