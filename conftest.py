"""Shared test fixtures for the entire project.

Broker-specific fixtures belong in each broker's conftest.py.
This root conftest holds fixtures used across multiple packages.
"""

from __future__ import annotations

from typing import Any

import pytest


def _ensure_dhanhq_sdk_aliases() -> None:
    """Provide backwards-compatible aliases for dhanhq SDK names.

    The installed dhanhq 2.2.0 SDK exposes ``MarketFeed`` / ``OrderUpdate`` and
    exposes its exchange-segment constants (``NSE``, ``MCX``, ...) only as class
    attributes. Some modules in this repo historically imported module-level
    constants and the legacy ``DhanFeed`` / ``OrderSocket`` names. This shim
    adds the missing names when they are absent, so the test suite can import
    the broker modules without requiring an older dhanhq release.
    """
    try:
        import dhanhq  # noqa: F401
        import dhanhq.marketfeed as _marketfeed
        import dhanhq.orderupdate as _orderupdate
    except Exception:
        return

    _SEGMENT_CONSTANTS = {
        "IDX": 0,
        "NSE": 1,
        "NSE_FNO": 2,
        "NSE_CURR": 3,
        "BSE": 4,
        "MCX": 5,
        "BSE_CURR": 7,
        "BSE_FNO": 8,
    }
    _REQUEST_CODE_CONSTANTS = {
        "Ticker": 15,
        "Quote": 17,
        "Depth": 19,
        "Full": 21,
    }

    for _name, _value in _SEGMENT_CONSTANTS.items():
        if not hasattr(_marketfeed, _name):
            setattr(_marketfeed, _name, _value)
    for _name, _value in _REQUEST_CODE_CONSTANTS.items():
        if not hasattr(_marketfeed, _name):
            setattr(_marketfeed, _name, _value)

    if not hasattr(_marketfeed, "DhanFeed"):
        class _StubDhanFeed:  # pragma: no cover - SDK version shim
            pass

        # The legacy ``DhanFeed`` class name must expose the same constants
        # the production class does. Modules like ``websocket.py`` access
        # ``SDKMarketFeed.Ticker`` etc. at call-time, so the stub needs
        # every constant the real class exposes.
        for _name, _value in _REQUEST_CODE_CONSTANTS.items():
            setattr(_StubDhanFeed, _name, _value)
        for _name, _value in _SEGMENT_CONSTANTS.items():
            setattr(_StubDhanFeed, _name, _value)
        _marketfeed.DhanFeed = _StubDhanFeed

        def _stub_run_forever(self, *args, **kwargs):
            return None

        _StubDhanFeed.run_forever = _stub_run_forever

    if not hasattr(_orderupdate, "OrderSocket"):
        class _StubOrderSocket:  # pragma: no cover - SDK version shim
            def __init__(self, *args, **kwargs):
                self.args = args
                self.kwargs = kwargs

        _orderupdate.OrderSocket = _StubOrderSocket


_ensure_dhanhq_sdk_aliases()


@pytest.fixture(autouse=True)
def _dhanhq_sdk_aliases_session():
    """Re-apply the SDK shim before each test in case a module re-imported
    the SDK symbols from a fresh state."""
    _ensure_dhanhq_sdk_aliases()
    yield


class FakeHttpClient:
    """Drop-in replacement for any broker HTTP client in unit tests.

    Records every request and returns pre-configured responses.
    Broker-specific conftest.py files may subclass this if they
    need broker-specific methods.
    """

    def __init__(
        self, client_id: str = "TEST_CLIENT", access_token: str = "TEST_TOKEN"
    ):
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


@pytest.fixture
def fake_http_client() -> FakeHttpClient:
    return FakeHttpClient()
