"""TDD tests for Dhan order stream functionality.

Tests order stream WebSocket client, event normalization, and provider.
"""

from unittest.mock import MagicMock, patch

from brokers.dhan.websocket.order_stream import (
    DhanOrderEventNormalizer,
    DhanOrderStreamWebSocketClient,
    OrderEventType,
)


class TestOrderEventType:
    def test_order_event_type_values(self):
        assert OrderEventType.ORDER_PLACED == "order_placed"
        assert OrderEventType.ORDER_MODIFIED == "order_modified"
        assert OrderEventType.ORDER_CANCELLED == "order_cancelled"
        assert OrderEventType.ORDER_FILLED == "order_filled"
        assert OrderEventType.ORDER_STATUS_UPDATE == "order_status_update"
        assert OrderEventType.ORDER_REJECTED == "order_rejected"


class TestDhanOrderEventNormalizer:
    def test_normalize_order_placed_event(self):
        raw_data = {
            "eventType": "order_placed",
            "orderId": "DHAN12345",
            "timestamp": 1640995200,
            "securityId": "2885",
            "quantity": 10,
            "price": 2500.0,
        }

        event = DhanOrderEventNormalizer.normalize_order_event(raw_data)

        assert event.event_type == OrderEventType.ORDER_PLACED
        assert event.order_id == "DHAN12345"
        assert event.order_data == raw_data

    def test_normalize_order_status_update_event(self):
        raw_data = {
            "eventType": "order_status_update",
            "orderId": "DHAN12345",
            "timestamp": 1640995200,
            "status": "filled",
            "filledQuantity": 10,
            "remainingQuantity": 0,
            "averagePrice": 2500.0,
        }

        event = DhanOrderEventNormalizer.normalize_order_event(raw_data)

        assert event.event_type == OrderEventType.ORDER_STATUS_UPDATE
        assert event.order_id == "DHAN12345"
        assert event.order_data == raw_data

    def test_normalize_unknown_event_type(self):
        raw_data = {
            "eventType": "unknown_event",
            "orderId": "DHAN12345",
            "timestamp": 1640995200,
        }

        event = DhanOrderEventNormalizer.normalize_order_event(raw_data)

        assert event.event_type == OrderEventType.ORDER_STATUS_UPDATE
        assert event.order_id == "DHAN12345"


class TestDhanOrderStreamWebSocketClient:
    def test_client_initialization(self):
        mock_url_resolver = MagicMock()
        mock_token_provider = MagicMock(return_value="test_token")
        mock_settings = MagicMock()

        client = DhanOrderStreamWebSocketClient(
            url_resolver=mock_url_resolver,
            token_provider=mock_token_provider,
            settings=mock_settings,
            timeout_seconds=15,
        )

        assert client._url_resolver == mock_url_resolver
        assert client._token_provider == mock_token_provider
        assert client._settings == mock_settings

    def test_connect(self):
        mock_connection_manager = MagicMock()
        mock_connection_manager.connect.return_value = True

        with patch(
            "brokers.dhan.websocket.order_stream.DhanOrderStreamConnectionManager",
            return_value=mock_connection_manager,
        ):
            client = DhanOrderStreamWebSocketClient(
                url_resolver=MagicMock(),
                token_provider=MagicMock(return_value="test_token"),
                settings=MagicMock(),
            )
            result = client.connect()
            assert result is True
            mock_connection_manager.connect.assert_called_once()

    def test_disconnect(self):
        mock_connection_manager = MagicMock()
        mock_connection_manager.disconnect.return_value = True

        with patch(
            "brokers.dhan.websocket.order_stream.DhanOrderStreamConnectionManager",
            return_value=mock_connection_manager,
        ):
            client = DhanOrderStreamWebSocketClient(
                url_resolver=MagicMock(),
                token_provider=MagicMock(return_value="test_token"),
                settings=MagicMock(),
            )
            result = client.disconnect()
            assert result is True
            mock_connection_manager.disconnect.assert_called_once()

    def test_subscribe(self):
        mock_connection_manager = MagicMock()
        mock_connection_manager.subscribe.return_value = True

        with patch(
            "brokers.dhan.websocket.order_stream.DhanOrderStreamConnectionManager",
            return_value=mock_connection_manager,
        ):
            client = DhanOrderStreamWebSocketClient(
                url_resolver=MagicMock(),
                token_provider=MagicMock(return_value="test_token"),
                settings=MagicMock(),
            )
            result = client.subscribe(["DHAN12345", "DHAN67890"])
            assert result is True
            mock_connection_manager.subscribe.assert_called_once_with(["DHAN12345", "DHAN67890"])

    def test_unsubscribe(self):
        mock_connection_manager = MagicMock()
        mock_connection_manager.unsubscribe.return_value = True

        with patch(
            "brokers.dhan.websocket.order_stream.DhanOrderStreamConnectionManager",
            return_value=mock_connection_manager,
        ):
            client = DhanOrderStreamWebSocketClient(
                url_resolver=MagicMock(),
                token_provider=MagicMock(return_value="test_token"),
                settings=MagicMock(),
            )
            result = client.unsubscribe(["DHAN12345", "DHAN67890"])
            assert result is True
            mock_connection_manager.unsubscribe.assert_called_once_with(["DHAN12345", "DHAN67890"])

    def test_is_connected(self):
        mock_connection_manager = MagicMock()
        mock_connection_manager.is_connected.return_value = True

        with patch(
            "brokers.dhan.websocket.order_stream.DhanOrderStreamConnectionManager",
            return_value=mock_connection_manager,
        ):
            client = DhanOrderStreamWebSocketClient(
                url_resolver=MagicMock(),
                token_provider=MagicMock(return_value="test_token"),
                settings=MagicMock(),
            )
            result = client.is_connected()
            assert result is True
            mock_connection_manager.is_connected.assert_called_once()

    def test_add_message_handler(self):
        mock_connection_manager = MagicMock()

        with patch(
            "brokers.dhan.websocket.order_stream.DhanOrderStreamConnectionManager",
            return_value=mock_connection_manager,
        ):
            client = DhanOrderStreamWebSocketClient(
                url_resolver=MagicMock(),
                token_provider=MagicMock(return_value="test_token"),
                settings=MagicMock(),
            )
            mock_handler = MagicMock()
            client.add_message_handler(mock_handler)
            mock_connection_manager.add_message_handler.assert_called_once_with(mock_handler)

    def test_add_connection_callback(self):
        mock_connection_manager = MagicMock()

        with patch(
            "brokers.dhan.websocket.order_stream.DhanOrderStreamConnectionManager",
            return_value=mock_connection_manager,
        ):
            client = DhanOrderStreamWebSocketClient(
                url_resolver=MagicMock(),
                token_provider=MagicMock(return_value="test_token"),
                settings=MagicMock(),
            )
            mock_callback = MagicMock()
            client.add_connection_callback(mock_callback)
            mock_connection_manager.add_connection_callback.assert_called_once_with(mock_callback)

    def test_get_subscriptions(self):
        mock_connection_manager = MagicMock()
        mock_connection_manager.get_subscriptions.return_value = {
            "DHAN12345": {"order_id": "DHAN12345"}
        }

        with patch(
            "brokers.dhan.websocket.order_stream.DhanOrderStreamConnectionManager",
            return_value=mock_connection_manager,
        ):
            client = DhanOrderStreamWebSocketClient(
                url_resolver=MagicMock(),
                token_provider=MagicMock(return_value="test_token"),
                settings=MagicMock(),
            )
            result = client.get_subscriptions()
            assert result == {"DHAN12345": {"order_id": "DHAN12345"}}
            mock_connection_manager.get_subscriptions.assert_called_once()
