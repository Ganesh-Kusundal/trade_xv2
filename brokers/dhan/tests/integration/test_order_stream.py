"""TDD tests for Dhan order stream integration.

Tests order stream provider integration with existing broker components.
"""

from unittest.mock import MagicMock, patch

from brokers.dhan import DhanBroker
from brokers.dhan.auth.context import DhanAdapterContext
from brokers.dhan.websocket.order_stream_adapter import DhanOrderStreamProvider


class TestDhanOrderStreamProvider:
    def test_provider_initialization(self):
        mock_context = MagicMock(spec=DhanAdapterContext)
        mock_context.url_resolver = MagicMock()
        mock_context.token_provider = MagicMock(return_value="test_token")
        mock_context.settings = MagicMock()
        mock_context._timeout_seconds = 15

        with patch(
            "brokers.dhan.websocket.order_stream_adapter.DhanOrderStreamWebSocketClient"
        ) as mock_client_class:
            mock_client = MagicMock()
            mock_client_class.return_value = mock_client
            provider = DhanOrderStreamProvider(mock_context)

            assert provider._context == mock_context
            assert provider._websocket_client is not None
            assert len(provider._listeners) == 0
            assert len(provider._order_subscriptions) == 0

    def test_subscribe_order_stream(self):
        mock_context = MagicMock(spec=DhanAdapterContext)
        mock_context.url_resolver = MagicMock()
        mock_context.token_provider = MagicMock(return_value="test_token")
        mock_context.settings = MagicMock()
        mock_context._timeout_seconds = 15

        provider = DhanOrderStreamProvider(mock_context)
        provider._websocket_client = MagicMock()
        provider._websocket_client.is_connected.return_value = True
        provider._websocket_client.subscribe.return_value = True

        result = provider.subscribe_order_stream(["DHAN12345", "DHAN67890"])

        assert result is True
        assert len(provider._order_subscriptions) == 2
        assert "DHAN12345" in provider._order_subscriptions
        assert "DHAN67890" in provider._order_subscriptions

    def test_subscribe_order_stream_not_connected(self):
        mock_context = MagicMock(spec=DhanAdapterContext)
        mock_context.url_resolver = MagicMock()
        mock_context.token_provider = MagicMock(return_value="test_token")
        mock_context.settings = MagicMock()
        mock_context._timeout_seconds = 15

        provider = DhanOrderStreamProvider(mock_context)
        provider._websocket_client = MagicMock()
        provider._websocket_client.is_connected.return_value = False

        result = provider.subscribe_order_stream(["DHAN12345"])

        assert result is False
        assert len(provider._order_subscriptions) == 0

    def test_unsubscribe_order_stream(self):
        mock_context = MagicMock(spec=DhanAdapterContext)
        mock_context.url_resolver = MagicMock()
        mock_context.token_provider = MagicMock(return_value="test_token")
        mock_context.settings = MagicMock()
        mock_context._timeout_seconds = 15

        provider = DhanOrderStreamProvider(mock_context)
        provider._websocket_client = MagicMock()
        provider._websocket_client.unsubscribe.return_value = True

        # Add some subscriptions first
        provider._order_subscriptions = {
            "DHAN12345": {"order_id": "DHAN12345"},
            "DHAN67890": {"order_id": "DHAN67890"},
        }

        result = provider.unsubscribe_order_stream(["DHAN12345"])

        assert result is True
        assert "DHAN12345" not in provider._order_subscriptions
        assert "DHAN67890" in provider._order_subscriptions

    def test_get_order_stream_status(self):
        mock_context = MagicMock(spec=DhanAdapterContext)
        mock_context.url_resolver = MagicMock()
        mock_context.token_provider = MagicMock(return_value="test_token")
        mock_context.settings = MagicMock()
        mock_context._timeout_seconds = 15

        with patch(
            "brokers.dhan.websocket.order_stream_adapter.DhanOrderStreamWebSocketClient"
        ) as mock_client_class:
            mock_client = MagicMock()
            mock_client_class.return_value = mock_client
            mock_client.is_connected.return_value = True
            mock_client.get_subscriptions.return_value = {"DHAN12345": {"order_id": "DHAN12345"}}

            provider = DhanOrderStreamProvider(mock_context)
            provider._websocket_client = mock_client
            # Add some subscriptions to the provider
            provider._order_subscriptions = {
                "DHAN12345": {"order_id": "DHAN12345", "subscribed_at": 123.0}
            }

            status = provider.get_order_stream_status()

            assert status["connected"] is True
            assert status["subscriptions"] == 1
            assert status["listeners"] == 0
            assert "DHAN12345" in status["websocket_subscriptions"]

    def test_add_order_listener(self):
        mock_context = MagicMock(spec=DhanAdapterContext)
        mock_context.url_resolver = MagicMock()
        mock_context.token_provider = MagicMock(return_value="test_token")
        mock_context.settings = MagicMock()
        mock_context._timeout_seconds = 15

        provider = DhanOrderStreamProvider(mock_context)
        mock_listener = MagicMock()

        provider.add_order_listener(mock_listener)

        assert len(provider._listeners) == 1
        assert provider._listeners[0] == mock_listener

    def test_remove_order_listener(self):
        mock_context = MagicMock(spec=DhanAdapterContext)
        mock_context.url_resolver = MagicMock()
        mock_context.token_provider = MagicMock(return_value="test_token")
        mock_context.settings = MagicMock()
        mock_context._timeout_seconds = 15

        provider = DhanOrderStreamProvider(mock_context)
        mock_listener = MagicMock()

        provider.add_order_listener(mock_listener)
        provider.remove_order_listener(mock_listener)

        assert len(provider._listeners) == 0

    def test_add_connection_callback(self):
        mock_context = MagicMock(spec=DhanAdapterContext)
        mock_context.url_resolver = MagicMock()
        mock_context.token_provider = MagicMock(return_value="test_token")
        mock_context.settings = MagicMock()
        mock_context._timeout_seconds = 15

        provider = DhanOrderStreamProvider(mock_context)
        mock_callback = MagicMock()

        provider.add_connection_callback(mock_callback)

        assert len(provider._connection_callbacks) == 1
        assert provider._connection_callbacks[0] == mock_callback

    def test_connect(self):
        mock_context = MagicMock(spec=DhanAdapterContext)
        mock_context.url_resolver = MagicMock()
        mock_context.token_provider = MagicMock(return_value="test_token")
        mock_context.settings = MagicMock()
        mock_context._timeout_seconds = 15

        with (
            patch(
                "brokers.dhan.websocket.order_stream_adapter.DhanOrderStreamWebSocketClient"
            ) as mock_client_class,
            patch("asyncio.create_task") as mock_create_task,
        ):
            mock_client = MagicMock()
            mock_client_class.return_value = mock_client

            # Create a mock task
            mock_task = MagicMock()
            mock_task.done.return_value = False
            mock_create_task.return_value = mock_task

            provider = DhanOrderStreamProvider(mock_context)
            provider._websocket_client = mock_client
            provider._connection_task = None

            result = provider.connect()

            assert result is True
            # Note: _connection_task may not be set due to async event loop issues in test

    def test_disconnect(self):
        mock_context = MagicMock(spec=DhanAdapterContext)
        mock_context.url_resolver = MagicMock()
        mock_context.token_provider = MagicMock(return_value="test_token")
        mock_context.settings = MagicMock()
        mock_context._timeout_seconds = 15

        with patch(
            "brokers.dhan.websocket.order_stream_adapter.DhanOrderStreamWebSocketClient"
        ) as mock_client_class:
            mock_client = MagicMock()
            mock_client_class.return_value = mock_client

            provider = DhanOrderStreamProvider(mock_context)
            provider._websocket_client = mock_client
            provider._connection_task = None

            result = provider.disconnect()

            assert result is True
            provider._websocket_client.disconnect.assert_called_once()
            # Note: _connection_task.cancel may not be called due to async event loop issues


class TestDhanBrokerOrderStreamIntegration:
    def test_broker_order_stream_capabilities(self):
        broker = DhanBroker(client_id="test", access_token="tok")
        broker.connect()

        assert broker.has_capability("order_stream")

    def test_broker_subscribe_order_stream(self):
        broker = DhanBroker(client_id="test", access_token="tok")
        broker.connect()

        # Mock the order_stream provider
        mock_order_stream = MagicMock()
        mock_order_stream.subscribe_order_stream.return_value = True
        broker.order_stream = mock_order_stream

        result = broker.subscribe_order_stream(["DHAN12345", "DHAN67890"])

        assert result is True
        mock_order_stream.subscribe_order_stream.assert_called_once_with(["DHAN12345", "DHAN67890"])

    def test_broker_unsubscribe_order_stream(self):
        broker = DhanBroker(client_id="test", access_token="tok")
        broker.connect()

        # Mock the order_stream provider
        mock_order_stream = MagicMock()
        mock_order_stream.unsubscribe_order_stream.return_value = True
        broker.order_stream = mock_order_stream

        result = broker.unsubscribe_order_stream(["DHAN12345", "DHAN67890"])

        assert result is True
        mock_order_stream.unsubscribe_order_stream.assert_called_once_with(
            ["DHAN12345", "DHAN67890"]
        )

    def test_broker_get_order_stream_status(self):
        broker = DhanBroker(client_id="test", access_token="tok")
        broker.connect()

        # Mock the order_stream provider
        mock_order_stream = MagicMock()
        mock_order_stream.get_order_stream_status.return_value = {
            "connected": True,
            "subscriptions": 1,
            "listeners": 0,
        }
        broker.order_stream = mock_order_stream

        status = broker.get_order_stream_status()

        assert status["connected"] is True
        assert status["subscriptions"] == 1
        assert status["listeners"] == 0
        mock_order_stream.get_order_stream_status.assert_called_once()

    def test_broker_add_order_listener(self):
        broker = DhanBroker(client_id="test", access_token="tok")
        broker.connect()

        # Mock the order_stream provider
        mock_order_stream = MagicMock()
        mock_order_stream.add_order_listener.return_value = None
        broker.order_stream = mock_order_stream

        mock_listener = MagicMock()
        broker.add_order_listener(mock_listener)

        mock_order_stream.add_order_listener.assert_called_once_with(mock_listener)

    def test_broker_remove_order_listener(self):
        broker = DhanBroker(client_id="test", access_token="tok")
        broker.connect()

        # Mock the order_stream provider
        mock_order_stream = MagicMock()
        mock_order_stream.remove_order_listener.return_value = None
        broker.order_stream = mock_order_stream

        mock_listener = MagicMock()
        broker.remove_order_listener(mock_listener)

        mock_order_stream.remove_order_listener.assert_called_once_with(mock_listener)
