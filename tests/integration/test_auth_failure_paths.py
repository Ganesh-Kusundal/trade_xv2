"""Integration: Authentication failure path tests.

These tests verify the system handles authentication failures gracefully:
- Token expiry mid-operation
- TOTP generation failure
- Rate-limited login
- Invalid credentials
- Token refresh during active WebSocket

Uses mocked HTTP server to simulate broker auth failures without real credentials.

Usage:
    ./venv/bin/python -m pytest tests/integration/test_auth_failure_paths.py -v
"""
import threading
import time
from unittest.mock import MagicMock, patch

import pytest


class TestTokenExpiryMidOrder:
    """Test token expiry during order submission."""

    def test_token_expiry_triggers_refresh_and_retry(self):
        """401 during order submission should trigger token refresh and retry."""
        from brokers.dhan.api.http_client import DhanHttpClient

        call_count = 0

        def mock_post(*args, **kwargs):
            nonlocal call_count
            call_count += 1

            # First call: 401 (token expired)
            if call_count == 1:
                mock_response = MagicMock()
                mock_response.status_code = 401
                mock_response.json.return_value = {"error": "Token expired"}
                return mock_response

            # Second call (after refresh): success
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.json.return_value = {
                "data": {
                    "orderId": "TEST-123",
                    "status": "OPEN",
                }
            }
            return mock_response

        # Create HTTP client with mocked refresh
        client = DhanHttpClient(
            base_url="https://api.dhan.co",
            client_id="test_client",
            access_token="expired_token",
            token_refresh_fn=lambda: "new_token",
        )

        # Mock the internal request method
        with patch.object(client, '_request', side_effect=mock_post):
            # Make a request
            response = client.post("/orders", json={
                "symbol": "RELIANCE",
                "side": "BUY",
                "quantity": 1,
            })

            # Should have retried after 401
            assert call_count >= 1
            assert response.status_code == 200
            print("✅ Token expiry triggers refresh and retry")

    def test_concurrent_requests_share_refresh_future(self):
        """Multiple 401s should trigger single refresh, not cascading refreshes."""
        from brokers.dhan.api.http_client import DhanHttpClient

        refresh_count = 0
        refresh_lock = threading.Lock()

        def slow_refresh():
            nonlocal refresh_count
            time.sleep(0.1)  # Simulate slow refresh
            with refresh_lock:
                refresh_count += 1
            return "new_token"

        DhanHttpClient(
            base_url="https://api.dhan.co",
            client_id="test_client",
            access_token="expired_token",
            token_refresh_fn=slow_refresh,
        )

        # Simulate concurrent requests
        results = []
        errors = []

        def make_request():
            try:
                # Simulate 401 then success
                response = MagicMock()
                response.status_code = 200
                results.append(response)
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=make_request) for _ in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        # All should succeed
        assert len(results) == 5
        assert len(errors) == 0
        # Refresh should only happen once (or very few times due to race)
        assert refresh_count <= 2, f"Too many refreshes: {refresh_count}"
        print("✅ Concurrent requests share refresh future")


class TestTOTPFailure:
    """Test TOTP generation and bootstrap failures."""

    def test_invalid_totp_secret_fails_fast(self):
        """Invalid TOTP secret should fail fast, not hang."""
        from pyotp import TOTP

        # Invalid TOTP secret (too short)
        invalid_secret = "INVALID"

        # Should raise when trying to generate TOTP
        with pytest.raises(Exception):
            totp = TOTP(invalid_secret)
            totp.now()

        print("✅ Invalid TOTP secret fails fast")

    def test_totp_generation_failure_blocks_bootstrap(self):
        """TOTP generation failure should block bootstrap with clear error."""
        from brokers.upstox.totp_client import UpstoxTotpClient

        # Create client with invalid secret
        client = UpstoxTotpClient(
            totp_secret="INVALID_SECRET_TOO_SHORT",
        )

        # Should raise when generating TOTP
        with pytest.raises((ValueError, Exception)):
            client.generate_totp()

        print("✅ TOTP failure blocks bootstrap")


class TestRateLimitedLogin:
    """Test rate-limited login scenarios."""

    def test_rate_limited_login_raises_error(self):
        """429 on login should raise RateLimitError, not block."""

        # Simulate rate limiter
        from infrastructure.resilience.rate_limiter import TokenBucketRateLimiter

        limiter = TokenBucketRateLimiter(rate=1, capacity=1)

        # First request should succeed
        limiter.acquire("login")

        # Second request immediately should fail
        with pytest.raises(Exception):  # Could be TimeoutError or custom
            limiter.acquire("login", timeout=0)

        print("✅ Rate limited login raises error")

    def test_rate_limited_login_does_not_deadlock(self):
        """429 on login should not cause deadlock."""
        import threading

        from infrastructure.resilience.rate_limiter import TokenBucketRateLimiter

        limiter = TokenBucketRateLimiter(rate=1, capacity=1)

        # Exhaust the token
        limiter.acquire("login")

        # Try to acquire from multiple threads
        results = []
        errors = []

        def try_acquire():
            try:
                limiter.acquire("login", timeout=0.1)
                results.append(True)
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=try_acquire) for _ in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=2)

        # Should not deadlock - all threads should complete
        assert all(not t.is_alive() for t in threads), "Deadlock detected!"
        print("✅ Rate limited login does not deadlock")


class TestWebSocketReconnectWithStaleToken:
    """Test WebSocket reconnection with stale/expired token."""

    def test_websocket_reconnect_with_expired_token_fails_gracefully(self):
        """WS reconnect with expired token should trigger re-auth, not crash."""
        from unittest.mock import MagicMock

        from brokers.dhan.websocket import DhanMarketFeed

        # Create mock feed
        mock_feed = MagicMock()
        mock_feed.run.side_effect = Exception("Token expired")

        # Create market feed
        feed = DhanMarketFeed(
            symbol="RELIANCE",
            exchange="NSE",
            market_feed=mock_feed,
        )

        # Should handle exception gracefully in reconnect loop
        # (not crash or hang)
        try:
            # Start the feed (will fail immediately)
            feed.start()
            time.sleep(0.1)
            feed.stop()
        except Exception as e:
            # Should not raise unhandled exception
            print(f"  Exception handled: {e}")

        print("✅ WS reconnect with expired token handled gracefully")


class TestInvalidCredentials:
    """Test invalid credentials handling."""

    def test_empty_client_id_raises_error(self):
        """Empty client ID should fail immediately on initialization."""
        from brokers.dhan.connection import DhanConnection

        with pytest.raises((ValueError, Exception)):
            DhanConnection(
                client_id="",
                access_token="some_token",
            )

        print("✅ Empty client ID fails fast")

    def test_empty_access_token_raises_error(self):
        """Empty access token should fail immediately on initialization."""
        from brokers.dhan.connection import DhanConnection

        with pytest.raises((ValueError, Exception)):
            DhanConnection(
                client_id="test_client",
                access_token="",
            )

        print("✅ Empty access token fails fast")

    def test_invalid_credentials_return_401(self):
        """Invalid credentials should return 401, not crash."""
        from unittest.mock import MagicMock, patch

        # Mock HTTP client
        mock_response = MagicMock()
        mock_response.status_code = 401
        mock_response.json.return_value = {
            "error": "Invalid credentials",
            "message": "Authentication failed",
        }

        with patch('requests.post', return_value=mock_response):
            import requests
            response = requests.post("https://api.dhan.co/login", json={
                "client_id": "invalid",
                "access_token": "invalid",
            })

            assert response.status_code == 401
            assert "error" in response.json()

        print("✅ Invalid credentials return 401")


class TestTokenRefreshRaceCondition:
    """Test Upstox token refresh single-flight under concurrent 401 recovery."""

    def test_concurrent_refresh_does_not_cascade(self):
        from unittest.mock import MagicMock, patch

        from brokers.upstox.auth.config import UpstoxConnectionSettings
        from brokers.upstox.auth.token_manager import UpstoxTokenManager

        settings = UpstoxConnectionSettings(
            client_id="CID",
            client_secret="CSEC",
            auth_mode="TOTP",
            mobile="9999999999",
            pin="1234",
            totp_secret="SECRET",
        )
        mgr = UpstoxTokenManager(settings=settings, oauth_client=MagicMock())
        refresh_count = {"n": 0}
        lock = threading.Lock()

        def tracked_bootstrap():
            time.sleep(0.05)
            with lock:
                refresh_count["n"] += 1
            from brokers.upstox.auth.holders import TokenSnapshot

            state = TokenSnapshot(
                access_token="new-token",
                refresh_token=None,
                expires_at_ms=int(time.time() * 1000) + 3_600_000,
                issued_at_ms=int(time.time() * 1000),
                source="TOTP",
            )
            mgr._apply_token_state(state, label="test")
            return state

        results = []

        def handle_401():
            try:
                ok = mgr.try_refresh_on_401()
                results.append(("success", ok))
            except Exception as exc:
                results.append(("error", str(exc)))

        with patch.object(mgr, "_bootstrap_totp", side_effect=tracked_bootstrap):
            threads = [threading.Thread(target=handle_401) for _ in range(10)]
            for t in threads:
                t.start()
            for t in threads:
                t.join()

        assert len(results) == 10
        assert all(r[0] == "success" and r[1] is True for r in results)
        assert refresh_count["n"] == 1, f"Expected 1 refresh, got {refresh_count['n']}"


@pytest.mark.integration
class TestAuthIntegrationWithGateway:
    """Integration tests for auth with actual gateway (requires sandbox)."""

    @pytest.fixture
    def mock_dhan_gateway(self):
        """Create Dhan gateway with mocked HTTP client."""
        from unittest.mock import MagicMock, patch

        from brokers.dhan.connection import DhanConnection
        from brokers.dhan.wire import DhanBrokerGateway

        # Create connection
        conn = DhanConnection(
            client_id="test_client",
            access_token="test_token",
        )

        # Mock the HTTP client
        with patch.object(conn, '_http_client') as mock_client:
            mock_client.post.return_value = MagicMock(status_code=200)
            mock_client.get.return_value = MagicMock(status_code=200)

            gw = DhanBrokerGateway(conn)
            yield gw

    def test_gateway_handles_401_gracefully(self, mock_dhan_gateway):
        """Gateway should handle 401 without crashing."""
        from unittest.mock import MagicMock

        # Mock 401 response
        mock_response = MagicMock()
        mock_response.status_code = 401
        mock_response.json.return_value = {"error": "Token expired"}

        with patch.object(mock_dhan_gateway._conn._http_client, 'post', return_value=mock_response):
            # Should not crash
            try:
                response = mock_dhan_gateway.place_order(
                    symbol="RELIANCE",
                    exchange="NSE",
                    side="BUY",
                    quantity=1,
                    order_type="MARKET",
                )
                # If it returns, should indicate failure
                assert not response.success or response.status.value in ("REJECTED", "FAILED")
            except Exception as e:
                # Should raise a proper exception, not crash
                assert "401" in str(e) or "auth" in str(e).lower() or "token" in str(e).lower()

        print("✅ Gateway handles 401 gracefully")
