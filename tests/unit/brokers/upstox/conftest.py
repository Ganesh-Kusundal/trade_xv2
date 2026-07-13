"""Unit test conftest — shared fixtures for the Upstox unit test suite.

Key fixture: ``_reset_account_connection_registry`` (autouse)
    ``UpstoxBrokerFactory.create()`` now reuses one gateway per
    ``(broker_id, client_id)`` via ``AccountConnectionRegistry`` (see
    factory.py) so repeated ``bootstrap_gateway()`` calls in the same
    process don't reconnect. Tests that construct multiple gateways with
    the same mocked ``client_id`` would otherwise get a cached instance
    from a prior test back instead of a fresh one. Mirrors the Dhan unit
    suite's equivalent fixture.
"""

from __future__ import annotations

import pytest

from brokers.common.identity.account_registry import AccountConnectionRegistry


@pytest.fixture(autouse=True)
def _reset_account_connection_registry():
    AccountConnectionRegistry.release_all()
    yield
    AccountConnectionRegistry.release_all()
