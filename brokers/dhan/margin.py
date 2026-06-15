"""Margin adapter."""

from __future__ import annotations

from brokers.dhan.http_client import DhanHttpClient
from brokers.dhan.resolver import SymbolResolver


class MarginAdapter:
    def __init__(self, client: DhanHttpClient, resolver: SymbolResolver):
        self._client = client
        self._resolver = resolver

    def calculate(self, payload: dict) -> dict:
        return self._client.post("/margincalculator", json=payload)
