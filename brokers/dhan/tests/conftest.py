"""Shared test fixtures for brokers.dhan tests."""

from __future__ import annotations

from typing import Any

import pytest

from brokers.dhan.resolver import SymbolResolver


# ---------------------------------------------------------------------------
# Fake HTTP client — sync mock replacing DhanHttpClient
# ---------------------------------------------------------------------------


class FakeHttpClient:
    """Drop-in replacement for DhanHttpClient in unit tests.

    Records every request and returns pre-configured responses.
    """

    def __init__(self, client_id: str = "TEST_CLIENT", access_token: str = "TEST_TOKEN"):
        self.client_id = client_id
        self.access_token = access_token
        self._responses: dict[tuple[str, str], Any] = {}
        self._side_effects: dict[tuple[str, str], Exception] = {}
        self.calls: list[tuple[str, str, Any]] = []

    def set_response(self, method: str, path: str, response: Any) -> None:
        self._responses[(method, path)] = response

    def set_side_effect(self, method: str, path: str, exc: Exception) -> None:
        self._side_effects[(method, path)] = exc

    def post(self, path: str, json: Any = None) -> Any:
        self.calls.append(("POST", path, json))
        key = ("POST", path)
        if key in self._side_effects:
            raise self._side_effects[key]
        return self._responses.get(key, {})

    def get(self, path: str) -> Any:
        self.calls.append(("GET", path, None))
        key = ("GET", path)
        if key in self._side_effects:
            raise self._side_effects[key]
        return self._responses.get(key, {})

    def put(self, path: str, json: Any = None) -> Any:
        self.calls.append(("PUT", path, json))
        key = ("PUT", path)
        if key in self._side_effects:
            raise self._side_effects[key]
        return self._responses.get(key, {})

    def delete(self, path: str) -> Any:
        self.calls.append(("DELETE", path, None))
        key = ("DELETE", path)
        if key in self._side_effects:
            raise self._side_effects[key]
        return self._responses.get(key, {})

    def update_token(self, token: str) -> None:
        self.access_token = token

    def close(self) -> None:
        pass

    @property
    def call_count(self) -> int:
        return len(self.calls)

    def calls_for(self, method: str, path: str) -> list[Any]:
        return [j for m, p, j in self.calls if m == method and p == path]


# ---------------------------------------------------------------------------
# Sample instrument rows
# ---------------------------------------------------------------------------

SAMPLE_ROWS = [
    {
        "SEM_TRADING_SYMBOL": "NIFTY",
        "SEM_SMST_SECURITY_ID": "13",
        "SEM_EXM_EXCH_ID": "IDX_I",
        "SEM_INSTRUMENT_NAME": "INDEX",
        "SEM_LOT_UNITS": 1,
        "SEM_TICK_SIZE": 0.05,
    },
    {
        "SEM_TRADING_SYMBOL": "RELIANCE",
        "SEM_SMST_SECURITY_ID": "2885",
        "SEM_EXM_EXCH_ID": "NSE_EQ",
        "SEM_INSTRUMENT_NAME": "EQUITY",
        "SEM_LOT_UNITS": 1,
        "SEM_TICK_SIZE": 0.05,
    },
    {
        "SEM_TRADING_SYMBOL": "RELIANCE",
        "SEM_SMST_SECURITY_ID": "532",
        "SEM_EXM_EXCH_ID": "BSE_EQ",
        "SEM_INSTRUMENT_NAME": "EQUITY",
        "SEM_LOT_UNITS": 1,
        "SEM_TICK_SIZE": 0.05,
    },
    {
        "SEM_TRADING_SYMBOL": "NIFTY 26 JUN 25000 CE",
        "SEM_SMST_SECURITY_ID": "55000",
        "SEM_EXM_EXCH_ID": "NSE_FNO",
        "SEM_INSTRUMENT_NAME": "OPTIDX",
        "SEM_LOT_UNITS": 75,
        "SEM_TICK_SIZE": 0.05,
        "SEM_EXPIRY_DATE": "2026-06-26",
        "SEM_STRIKE_PRICE": 25000,
        "SEM_OPTION_TYPE": "CE",
        "SEM_CUSTOM_SYMBOL": "NIFTY 26 JUN 25000 CALL",
    },
    {
        "SEM_TRADING_SYMBOL": "NIFTY 26 JUN 25000 PE",
        "SEM_SMST_SECURITY_ID": "55001",
        "SEM_EXM_EXCH_ID": "NSE_FNO",
        "SEM_INSTRUMENT_NAME": "OPTIDX",
        "SEM_LOT_UNITS": 75,
        "SEM_TICK_SIZE": 0.05,
        "SEM_EXPIRY_DATE": "2026-06-26",
        "SEM_STRIKE_PRICE": 25000,
        "SEM_OPTION_TYPE": "PE",
        "SEM_CUSTOM_SYMBOL": "NIFTY 26 JUN 25000 PUT",
    },
    {
        "SEM_TRADING_SYMBOL": "NIFTY 26 JUN FUT",
        "SEM_SMST_SECURITY_ID": "55100",
        "SEM_EXM_EXCH_ID": "NSE_FNO",
        "SEM_INSTRUMENT_NAME": "FUTIDX",
        "SEM_LOT_UNITS": 75,
        "SEM_TICK_SIZE": 0.05,
        "SEM_EXPIRY_DATE": "2026-06-26",
        "SEM_CUSTOM_SYMBOL": "NIFTY",
    },
    {
        "SEM_TRADING_SYMBOL": "GOLD AUG FUT",
        "SEM_SMST_SECURITY_ID": "466583",
        "SEM_EXM_EXCH_ID": "MCX_COMM",
        "SEM_INSTRUMENT_NAME": "FUTCOM",
        "SEM_LOT_UNITS": 1,
        "SEM_TICK_SIZE": 1.0,
        "SEM_EXPIRY_DATE": "2026-08-05",
        "SEM_CUSTOM_SYMBOL": "GOLD",
    },
    {
        "SEM_TRADING_SYMBOL": "GOLD OCT FUT",
        "SEM_SMST_SECURITY_ID": "483079",
        "SEM_EXM_EXCH_ID": "MCX_COMM",
        "SEM_INSTRUMENT_NAME": "FUTCOM",
        "SEM_LOT_UNITS": 1,
        "SEM_TICK_SIZE": 1.0,
        "SEM_EXPIRY_DATE": "2026-10-05",
        "SEM_CUSTOM_SYMBOL": "GOLD",
    },
]


# ---------------------------------------------------------------------------
# Pytest fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def fake_client():
    return FakeHttpClient()


@pytest.fixture
def sample_rows():
    return list(SAMPLE_ROWS)


@pytest.fixture
def resolver(sample_rows):
    r = SymbolResolver()
    r.load_from_rows(sample_rows)
    return r
