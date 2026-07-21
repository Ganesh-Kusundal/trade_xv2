"""UpstoxBrokerFactory connection reuse — regression guard.

Every ``bootstrap_gateway("upstox", ...)`` call used to construct a brand
new ``UpstoxBroker`` (and therefore a new WebSocket connection + a fresh
feed-authorize request) unconditionally -- unlike Dhan, which already
shared one connection per account via ``AccountConnectionRegistry``.
Calling ``bootstrap_gateway`` more than once per process (a real pattern:
scripts, notebooks, repeated test setup) burned a connect/authorize cycle
every time and risked provider-side reconnect throttling. Fixed by routing
``UpstoxBrokerFactory.create()`` through the same registry Dhan uses.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from brokers.common.identity.account_registry import AccountConnectionRegistry
from brokers.providers.upstox.auth.config import UpstoxConnectionSettings
from brokers.providers.upstox.factory import UpstoxBrokerFactory


def _settings(client_id: str = "up-client") -> UpstoxConnectionSettings:
    return UpstoxConnectionSettings(client_id=client_id, access_token="access", auth_mode="STATIC")


def _create(settings: UpstoxConnectionSettings):
    mock_broker = MagicMock()
    mock_broker.token_manager = MagicMock()
    mock_broker.market_data_websocket = MagicMock()
    mock_broker.portfolio_stream = MagicMock()
    mock_broker.connect.return_value = True

    with (
        patch("brokers.providers.upstox.factory.UpstoxSettingsLoader.from_env", return_value=settings),
        patch("brokers.providers.upstox.factory.UpstoxBroker", return_value=mock_broker) as broker_cls,
        patch("brokers.providers.upstox.factory.UpstoxWireAdapter") as gateway_cls,
    ):
        gateway_cls.return_value = MagicMock()
        gateway = UpstoxBrokerFactory().create(load_instruments=False)
        return gateway, broker_cls


def test_second_create_reuses_gateway_for_same_client_id():
    gw1, broker_cls_1 = _create(_settings("up-client"))
    gw2, broker_cls_2 = _create(_settings("up-client"))

    assert gw1 is gw2, "second create() for the same client_id must reuse the cached gateway"
    # UpstoxBroker (the thing that owns the WS connection) must only be
    # constructed once -- the second create() must never reach it.
    broker_cls_2.assert_not_called()


def test_different_client_ids_get_different_gateways():
    gw1, _ = _create(_settings("up-client-a"))
    gw2, _ = _create(_settings("up-client-b"))

    assert gw1 is not gw2


def test_release_all_clears_cache_so_next_create_reconnects():
    gw1, _ = _create(_settings("up-client"))
    AccountConnectionRegistry.release_all()
    gw2, broker_cls_2 = _create(_settings("up-client"))

    assert gw1 is not gw2
    broker_cls_2.assert_called_once()
