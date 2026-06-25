"""Integration tests — WebSocket reconnect under network failure.

Uses a real local ``websockets`` server (no broker mocks) to simulate
connection drops and verify the depth feed reconnect loop and token
re-auth path recover automatically.
"""

from __future__ import annotations

import asyncio
import threading
import time
from urllib.parse import parse_qs, urlparse

import pytest

pytestmark = [
    pytest.mark.integration,
    pytest.mark.auth_integration,
]


def _wait_until(predicate, *, timeout: float = 8.0, interval: float = 0.05) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        if predicate():
            return True
        time.sleep(interval)
    return False


class _FlakyWebSocketServer:
    """Local WS server that drops connections to force client reconnect."""

    def __init__(self, *, drop_after_connect: int = 2) -> None:
        self._drop_after_connect = drop_after_connect
        self._connect_count = 0
        self._seen_paths: list[str] = []
        self._lock = threading.Lock()
        self._loop: asyncio.AbstractEventLoop | None = None
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()
        self.port: int = 0
        self.base_url: str = ""

    @property
    def connect_count(self) -> int:
        with self._lock:
            return self._connect_count

    @property
    def seen_tokens(self) -> list[str]:
        with self._lock:
            tokens: list[str] = []
            for path in self._seen_paths:
                query = parse_qs(urlparse(path).query)
                token = query.get("token", [""])[0]
                if token:
                    tokens.append(token)
            return tokens

    async def _handler(self, ws) -> None:
        path = ws.request.path
        with self._lock:
            self._connect_count += 1
            self._seen_paths.append(path)
            count = self._connect_count

        if count <= self._drop_after_connect:
            await asyncio.sleep(0.03)
            await ws.close()
            return

        try:
            while not self._stop.is_set():
                await asyncio.sleep(0.2)
        except asyncio.CancelledError:
            raise

    def start(self) -> None:
        import websockets

        async def _serve() -> None:
            async with websockets.serve(self._handler, "127.0.0.1", 0) as server:
                sock = server.sockets[0]
                self.port = sock.getsockname()[1]
                self.base_url = f"ws://127.0.0.1:{self.port}"
                while not self._stop.is_set():
                    await asyncio.sleep(0.05)

        def _thread_main() -> None:
            self._loop = asyncio.new_event_loop()
            asyncio.set_event_loop(self._loop)
            self._loop.run_until_complete(_serve())

        self._thread = threading.Thread(target=_thread_main, daemon=True, name="flaky-ws")
        self._thread.start()
        assert _wait_until(lambda: self.base_url != "", timeout=3.0), "WS server failed to start"

    def stop(self) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=3.0)


@pytest.fixture()
def flaky_ws_server():
    server = _FlakyWebSocketServer(drop_after_connect=3)
    server.start()
    try:
        yield server
    finally:
        server.stop()


class TestDepthFeedNetworkReconnect:
    def test_reconnects_after_server_drops_connection(self, flaky_ws_server):
        from brokers.dhan.depth_20 import DhanDepth20Feed

        feed = DhanDepth20Feed("TEST_CLIENT", "TOKEN_A")
        feed.ENDPOINT = flaky_ws_server.base_url

        feed.connect()
        try:
            assert _wait_until(
                lambda: flaky_ws_server.connect_count >= 2,
                timeout=10.0,
            ), f"expected reconnect, got {flaky_ws_server.connect_count} connects"
        finally:
            feed.stop()

    def test_token_refresh_reconnects_with_new_credentials(self, flaky_ws_server):
        from brokers.dhan.depth_20 import DhanDepth20Feed

        feed = DhanDepth20Feed("TEST_CLIENT", "TOKEN_A")
        feed.ENDPOINT = flaky_ws_server.base_url

        feed.connect()
        try:
            assert _wait_until(
                lambda: "TOKEN_A" in flaky_ws_server.seen_tokens,
                timeout=8.0,
            ), "initial connection never used TOKEN_A"

            feed.update_token("TOKEN_B")

            assert _wait_until(
                lambda: "TOKEN_B" in flaky_ws_server.seen_tokens,
                timeout=10.0,
            ), f"reconnect never picked up TOKEN_B; seen={flaky_ws_server.seen_tokens}"
            assert feed._access_token == "TOKEN_B"
        finally:
            feed.stop()

    def test_websocket_auth_coordinator_notifies_connection_depth_feeds(
        self,
        flaky_ws_server,
    ):
        from brokers.common.connection.websocket_auth_coordinator import (
            WebSocketAuthCoordinator,
        )
        from brokers.dhan.depth_20 import DhanDepth20Feed

        feed = DhanDepth20Feed("TEST_CLIENT", "TOKEN_A")
        feed.ENDPOINT = flaky_ws_server.base_url
        feed.connect()

        class _Conn:
            depth_20_feed = feed

        try:
            assert _wait_until(
                lambda: flaky_ws_server.connect_count >= 1,
                timeout=8.0,
            )

            before = flaky_ws_server.connect_count
            WebSocketAuthCoordinator.notify_depth_feeds(_Conn(), "TOKEN_C")

            assert feed._access_token == "TOKEN_C"
            assert _wait_until(
                lambda: flaky_ws_server.connect_count > before
                and "TOKEN_C" in flaky_ws_server.seen_tokens,
                timeout=10.0,
            ), "coordinator did not force reconnect with new token"
        finally:
            feed.stop()
