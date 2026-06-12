"""Upstox market intelligence aggregator — produces a
``MarketIntelligenceSnapshot`` in one call.

Mirrors Trade_J ``MarketIntelligenceSnapshot`` aggregator.
"""

from __future__ import annotations

import contextlib
from datetime import datetime
from typing import Any

from brokers.common.core.models import MarketIntelligenceSnapshot
from brokers.upstox.market_intelligence.client import UpstoxMarketIntelligenceClient


class UpstoxMarketIntelligenceSnapshotBuilder:
    def __init__(self, client: UpstoxMarketIntelligenceClient) -> None:
        self._client = client

    def get_snapshot(
        self,
        underlying: str,
        *,
        expiry: str | None = None,
        date: str | None = None,
    ) -> MarketIntelligenceSnapshot:
        snapshot = MarketIntelligenceSnapshot(underlying=underlying, as_of=datetime.now())
        try:
            pcr_body = self._client.get_pcr(underlying)
            snapshot.pcr = _extract_pcr(pcr_body)
        except Exception:
            pass
        if expiry and date:
            try:
                mp = self._client.get_max_pain(underlying, expiry, date)
                snapshot.max_pain = _extract_decimal(mp, "max_pain")
                insights = mp.get("data") if isinstance(mp, dict) else None
                if isinstance(insights, dict):
                    snapshot.max_pain_insights = [insights]
            except Exception:
                pass
            try:
                oi_body = self._client.get_oi(underlying, expiry, date)
                snapshot.total_call_oi = _extract_int(oi_body, "total_call_oi", "ce_oi")
                snapshot.total_put_oi = _extract_int(oi_body, "total_put_oi", "pe_oi")
                data = oi_body.get("data") if isinstance(oi_body, dict) else None
                if isinstance(data, list):
                    snapshot.oi_by_strike = data
            except Exception:
                pass
        with contextlib.suppress(Exception):
            snapshot.fii_flow = self._client.get_fii_flow()
        with contextlib.suppress(Exception):
            snapshot.dii_flow = self._client.get_dii_flow()
        with contextlib.suppress(Exception):
            snapshot.smartlist_futures = self._client.get_smartlist_futures()
        with contextlib.suppress(Exception):
            snapshot.smartlist_options = self._client.get_smartlist_options()
        return snapshot


def _extract_pcr(body: Any) -> Any:
    if not isinstance(body, dict):
        return None
    data = body.get("data")
    if isinstance(data, dict):
        return data.get("pcr")
    if isinstance(data, list) and data:
        first = data[0]
        if isinstance(first, dict):
            return first.get("pcr")
    return body.get("pcr")


def _extract_decimal(body: Any, key: str) -> Any:
    if not isinstance(body, dict):
        return None
    data = body.get("data")
    if isinstance(data, dict):
        return data.get(key)
    return body.get(key)


def _extract_int(body: Any, *keys: str) -> Any:
    if not isinstance(body, dict):
        return None
    data = body.get("data")
    for k in keys:
        if isinstance(data, dict) and k in data:
            return data.get(k)
        if k in body:
            return body.get(k)
    return None
