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

import pytest

from brokers.providers.dhan.resolver import SymbolResolver
from brokers.providers.dhan.streaming.connection_admission import NoopAdmission
from tests.support.brokers.dhan.fixtures import SAMPLE_ROWS, FakeHttpClient


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

    with (
        mock.patch(
            "brokers.providers.dhan.websocket.connection.MarketFeedConnectionAdmission",
            side_effect=lambda *args, **kwargs: NoopAdmission(),
        ),
        mock.patch(
            "brokers.providers.dhan.websocket.market_feed.MarketFeedConnectionAdmission",
            side_effect=lambda *args, **kwargs: NoopAdmission(),
        ),
    ):
        yield
