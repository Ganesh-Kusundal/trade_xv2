"""Tests for WebSocket auto-reconnect."""

from __future__ import annotations

import threading
import time
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from plugins.brokers.common.ws_reconnect import ReconnectConfig, WsReconnectManager


class TestReconnectConfig:
    def test_default_config(self) -> None:
        config = ReconnectConfig()
        assert config.max_retries == 10
        assert config.base_delay == 1.0
        assert config.max_delay == 30.0
        assert config.exponential_base == 2.0

    def test_custom_config(self) -> None:
        config = ReconnectConfig(max_retries=5, base_delay=0.5)
        assert config.max_retries == 5
        assert config.base_delay == 0.5


class TestWsReconnectManager:
    def test_initial_state(self) -> None:
        manager = WsReconnectManager()
        assert manager.is_connected is False

    def test_on_connect_sets_connected(self) -> None:
        manager = WsReconnectManager()
        manager.on_connect()
        assert manager.is_connected is True

    def test_on_close_sets_disconnected(self) -> None:
        manager = WsReconnectManager()
        manager.on_connect()
        manager.on_close()
        assert manager.is_connected is False

    def test_on_connect_resets_retry_count(self) -> None:
        manager = WsReconnectManager()
        manager._retry_count = 5
        manager.on_connect()
        assert manager._retry_count == 0

    def test_reconnect_success(self) -> None:
        manager = WsReconnectManager(ReconnectConfig(max_retries=3, base_delay=0.01))
        reconnect_fn = MagicMock()
        replay_fn = MagicMock()

        manager.on_disconnect(reconnect_fn, replay_fn)

        reconnect_fn.assert_called_once()
        replay_fn.assert_called_once()
        assert manager.is_connected is True

    def test_reconnect_with_initial_failure(self) -> None:
        manager = WsReconnectManager(ReconnectConfig(max_retries=3, base_delay=0.01))
        call_count = 0

        def failing_then_succeeding() -> None:
            nonlocal call_count
            call_count += 1
            if call_count < 2:
                raise ConnectionError("Connection refused")

        reconnect_fn = MagicMock(side_effect=failing_then_succeeding)
        replay_fn = MagicMock()

        manager.on_disconnect(reconnect_fn, replay_fn)

        assert reconnect_fn.call_count == 2
        replay_fn.assert_called_once()

    def test_reconnect_max_retries_exceeded(self) -> None:
        manager = WsReconnectManager(ReconnectConfig(max_retries=2, base_delay=0.01))
        reconnect_fn = MagicMock(side_effect=ConnectionError("Always fail"))
        replay_fn = MagicMock()

        with patch("plugins.brokers.common.ws_reconnect.time.sleep"):
            manager.on_disconnect(reconnect_fn, replay_fn)

        assert reconnect_fn.call_count == 2  # 2 retry attempts
        replay_fn.assert_not_called()
        assert manager.is_connected is False

    def test_thread_safety(self) -> None:
        manager = WsReconnectManager()
        errors: list[Exception] = []

        def connect_disconnect() -> None:
            try:
                manager.on_connect()
                assert manager.is_connected is True
                manager.on_close()
                assert manager.is_connected is False
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=connect_disconnect) for _ in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(errors) == 0

    def test_reset(self) -> None:
        manager = WsReconnectManager()
        manager._retry_count = 5
        manager._connected = True
        manager.reset()
        assert manager._retry_count == 0
        assert manager._connected is False
