"""Tests for api.middleware — rate limiting, path normalization, and metrics."""

from __future__ import annotations

from interface.api.middleware import (
    SKIP_PATHS,
    HttpRequestMetrics,
    _is_id_like,
    _normalise_path,
    _SlidingWindowCounter,
)


class TestNormalisePath:
    def test_numeric_segment(self):
        assert _normalise_path("/orders/12345") == "/orders/{id}"

    def test_uuid_like_segment(self):
        assert _normalise_path("/replay/sessions/abc-123/play") == "/replay/sessions/{id}/play"

    def test_non_id_segments_unchanged(self):
        assert _normalise_path("/api/v1/orders") == "/api/v1/orders"

    def test_mixed_segments(self):
        assert _normalise_path("/orders/42/items") == "/orders/{id}/items"

    def test_empty_path(self):
        assert _normalise_path("") == ""


class TestIsIdLike:
    def test_pure_digits(self):
        assert _is_id_like("12345") is True

    def test_alphanumeric_with_hyphen_and_digit(self):
        assert _is_id_like("abc-123") is True

    def test_plain_word(self):
        assert _is_id_like("orders") is False

    def test_empty_string(self):
        assert _is_id_like("") is False

    def test_word_with_hyphen_no_digit(self):
        assert _is_id_like("intra-day") is False


class TestSkipPaths:
    def test_health_paths_in_skip_set(self):
        assert "/api/v1/health" in SKIP_PATHS
        assert "/api/v1/health/readyz" in SKIP_PATHS

    def test_docs_in_skip_set(self):
        assert "/docs" in SKIP_PATHS

    def test_api_orders_not_in_skip_set(self):
        assert "/api/v1/orders" not in SKIP_PATHS


class TestSlidingWindowCounter:
    def test_allows_within_limit(self):
        counter = _SlidingWindowCounter(window_seconds=10.0)
        allowed, remaining = counter.is_allowed("client-1", max_requests=5)
        assert allowed is True
        assert remaining == 4

    def test_denies_when_exhausted(self):
        counter = _SlidingWindowCounter(window_seconds=10.0)
        for _ in range(5):
            counter.is_allowed("client-1", max_requests=5)
        allowed, remaining = counter.is_allowed("client-1", max_requests=5)
        assert allowed is False
        assert remaining == 0

    def test_different_clients_independent(self):
        counter = _SlidingWindowCounter(window_seconds=10.0)
        for _ in range(5):
            counter.is_allowed("client-1", max_requests=5)
        allowed, _ = counter.is_allowed("client-2", max_requests=5)
        assert allowed is True


class TestHttpRequestMetrics:
    def test_record_and_snapshot(self):
        m = HttpRequestMetrics()
        m.record("GET", "/orders", 200, 10.0)
        m.record("GET", "/orders", 200, 20.0)
        snap = m.snapshot()
        assert snap["total"]["GET|/orders|200"] == 2
        assert snap["duration_ms_sum"]["GET|/orders|200"] == 30.0
        assert snap["duration_ms_count"]["GET|/orders|200"] == 2

    def test_active_requests_gauge(self):
        m = HttpRequestMetrics()
        m.inc_active()
        m.inc_active()
        assert m.active_requests == 2
        m.dec_active()
        assert m.active_requests == 1

    def test_dec_active_floor_at_zero(self):
        m = HttpRequestMetrics()
        m.dec_active()
        assert m.active_requests == 0

    def test_render_prometheus(self):
        m = HttpRequestMetrics()
        m.record("GET", "/health", 200, 5.0)
        output = m.render_prometheus()
        assert "tradexv2_http_requests_total" in output
        assert 'method="GET"' in output
        assert "tradexv2_http_active_requests" in output
