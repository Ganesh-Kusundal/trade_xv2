"""Upstox market intelligence REST client (PCR / MaxPain / OI / FII / DII / Smartlist).

Mirrors Trade_J ``UpstoxMarketDataRestClient`` market-intelligence section.
"""

from __future__ import annotations

from typing import Any

from brokers.upstox.auth.urls import UpstoxApiUrlResolver


class UpstoxMarketIntelligenceClient:
    def __init__(self, http_client: Any, url_resolver: UpstoxApiUrlResolver) -> None:
        self._http = http_client
        self._urls = url_resolver

    def get_pcr(self, underlying: str, interval: str = "1d") -> dict[str, Any]:
        return self._http.get_json(
            self._urls.pcr_url(), params={"underlying": underlying, "interval": interval}
        )

    def get_max_pain(self, underlying: str, expiry: str, date: str) -> dict[str, Any]:
        return self._http.get_json(
            self._urls.max_pain_url(),
            params={"underlying": underlying, "expiry": expiry, "date": date},
        )

    def get_oi(self, underlying: str, expiry: str, date: str) -> dict[str, Any]:
        return self._http.get_json(
            self._urls.oi_url(),
            params={"underlying": underlying, "expiry": expiry, "date": date},
        )

    def get_fii_flow(self, segment: str = "ALL", interval: str = "1D") -> dict[str, Any]:
        return self._http.get_json(
            self._urls.fii_url(),
            params={"segment": segment, "interval": interval},
        )

    def get_dii_flow(self, interval: str = "1D") -> dict[str, Any]:
        return self._http.get_json(self._urls.dii_url(), params={"interval": interval})

    def get_smartlist_futures(self) -> list[dict[str, Any]]:
        body = self._http.get_json(self._urls.smartlist_futures_url())
        return _data_list(body)

    def get_smartlist_options(self, kind: str | None = None) -> list[dict[str, Any]]:
        params: dict[str, Any] = {}
        if kind:
            params["kind"] = kind
        body = self._http.get_json(self._urls.smartlist_options_url(), params=params)
        return _data_list(body)


def _data_list(body: Any) -> list[dict[str, Any]]:
    if not isinstance(body, dict):
        return []
    data = body.get("data")
    return data if isinstance(data, list) else []
