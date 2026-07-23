"""Tests for HTTP retry policies."""

from __future__ import annotations

import threading
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from plugins.brokers.common.retry import RetryConfig, RetryExhaustedError, RetryableHttpClient


class FakeHttpClient:
    """Test double for HttpClient."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, str, dict]] = []
        self.responses: list[tuple[int, Any]] = []
        self.call_index = 0

    def request(self, method: str, url: str, **kwargs: Any) -> tuple[int, Any]:
        self.calls.append((method, url, kwargs))
        if self.call_index < len(self.responses):
            result = self.responses[self.call_index]
            self.call_index += 1
            return result
        return (200, {"status": "ok"})


class TestRetryConfig:
    def test_default_config(self) -> None:
        config = RetryConfig()
        assert config.max_retries == 3
        assert config.base_delay == 0.5
        assert config.max_delay == 10.0
        assert config.jitter is True
        assert 429 in config.retryable_status

    def test_custom_config(self) -> None:
        config = RetryConfig(max_retries=5, base_delay=1.0, jitter=False)
        assert config.max_retries == 5
        assert config.base_delay == 1.0
        assert config.jitter is False


class TestRetryableHttpClient:
    def test_successful_request_no_retry(self) -> None:
        fake = FakeHttpClient()
        fake.responses = [(200, {"ok": True})]
        client = RetryableHttpClient(fake, RetryConfig(max_retries=3))

        status, body = client.request("GET", "https://api.example.com/test")

        assert status == 200
        assert body == {"ok": True}
        assert len(fake.calls) == 1

    def test_retry_on_429(self) -> None:
        fake = FakeHttpClient()
        fake.responses = [
            (429, {"error": "rate limited"}),
            (200, {"ok": True}),
        ]
        client = RetryableHttpClient(fake, RetryConfig(max_retries=3, jitter=False))

        with patch("plugins.brokers.common.retry.time.sleep"):
            status, body = client.request("GET", "https://api.example.com/test")

        assert status == 200
        assert len(fake.calls) == 2

    def test_retry_on_5xx(self) -> None:
        fake = FakeHttpClient()
        fake.responses = [
            (503, {"error": "service unavailable"}),
            (200, {"ok": True}),
        ]
        client = RetryableHttpClient(fake, RetryConfig(max_retries=3, jitter=False))

        with patch("plugins.brokers.common.retry.time.sleep"):
            status, body = client.request("GET", "https://api.example.com/test")

        assert status == 200
        assert len(fake.calls) == 2

    def test_no_retry_on_4xx_except_429(self) -> None:
        fake = FakeHttpClient()
        fake.responses = [(400, {"error": "bad request"})]
        client = RetryableHttpClient(fake, RetryConfig(max_retries=3))

        status, body = client.request("GET", "https://api.example.com/test")

        assert status == 400
        assert len(fake.calls) == 1

    def test_max_retries_exceeded(self) -> None:
        fake = FakeHttpClient()
        fake.responses = [(500, {"error": "server error"})] * 10
        client = RetryableHttpClient(fake, RetryConfig(max_retries=2, jitter=False))

        with patch("plugins.brokers.common.retry.time.sleep"):
            with pytest.raises(RetryExhaustedError):
                client.request("GET", "https://api.example.com/test")

        assert len(fake.calls) == 3  # 1 initial + 2 retries

    def test_exponential_backoff_delay(self) -> None:
        client = RetryableHttpClient(
            FakeHttpClient(),
            RetryConfig(base_delay=1.0, max_delay=10.0, exponential_base=2.0, jitter=False),
        )

        assert client._calc_delay(0) == 1.0
        assert client._calc_delay(1) == 2.0
        assert client._calc_delay(2) == 4.0
        assert client._calc_delay(3) == 8.0
        assert client._calc_delay(4) == 10.0  # capped at max_delay

    def test_jitter_adds_variation(self) -> None:
        client = RetryableHttpClient(
            FakeHttpClient(),
            RetryConfig(base_delay=1.0, jitter=True),
        )

        delays = [client._calc_delay(0) for _ in range(100)]
        assert all(0.5 <= d <= 1.0 for d in delays)
        assert len(set(delays)) > 1  # Should have variation

    def test_thread_safety(self) -> None:
        fake = FakeHttpClient()
        fake.responses = [(200, {"ok": True})] * 100
        client = RetryableHttpClient(fake, RetryConfig(max_retries=3))

        errors: list[Exception] = []

        def make_request() -> None:
            try:
                client.request("GET", "https://api.example.com/test")
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=make_request) for _ in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(errors) == 0
