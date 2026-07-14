"""Unit test conftest — shared fixtures for the Dhan unit test suite.

Key fixture: ``noop_admission`` (autouse, session scope)
    Patches ``MarketFeedConnectionAdmission`` with ``NoopAdmission`` for
    every unit test so that:
    - No ``fcntl`` lock files are created or contested.
    - No cooldown JSON files are written to the ``runtime/`` directory.
    - Tests that construct ``DhanMarketFeed`` directly never race on the
      host-wide admission lock when run in parallel.

    The real ``MarketFeedConnectionAdmission`` is tested separately in
    ``test_connection_admission.py`` (if present) with its own lock path.
"""

from __future__ import annotations

from typing import Any

import pytest

from brokers.dhan.resolver import SymbolResolver
from brokers.dhan.streaming.connection_admission import NoopAdmission
from tests.support.brokers.dhan.fixtures import SAMPLE_ROWS


class FakeHttpClient:
    """Drop-in replacement for DhanHttpClient in unit tests.

    Records every request and returns pre-configured responses. This is
    the ``fake_client``/``resolver`` fixture pair every test in this
    package depends on — previously lived in the deleted
    ``brokers/dhan/tests/conftest.py`` and was never rehomed when the
    suite moved to ``tests/unit/brokers/dhan/`` (see wave-2 rehoming).
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


@pytest.fixture(autouse=True, scope="session")
def noop_admission_patch():
    """Replace MarketFeedConnectionAdmission with NoopAdmission globally.

    Session-scoped so the patch is applied once for the entire test run and
    torn down at the end. Using ``pytest.MonkeyPatch`` at session scope
    requires the ``monkeypatch`` session fixture workaround below.
    """
    import unittest.mock as mock

    with mock.patch(
        "brokers.dhan.websocket.connection.MarketFeedConnectionAdmission",
        side_effect=lambda *args, **kwargs: NoopAdmission(),
    ), mock.patch(
        "brokers.dhan.websocket.market_feed.MarketFeedConnectionAdmission",
        side_effect=lambda *args, **kwargs: NoopAdmission(),
    ):
        yield

