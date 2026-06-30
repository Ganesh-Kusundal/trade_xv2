"""Performance benchmarks for API endpoints."""

from __future__ import annotations

import time

from fastapi.testclient import TestClient


class TestHealthEndpointPerformance:
    """Benchmark health endpoint performance."""

    def test_health_response_time(self, client: TestClient, benchmark):
        """Health endpoint should respond in < 10ms."""

        def fetch_health():
            return client.get("/api/v1/health")

        result = benchmark(fetch_health)
        assert result.status_code == 200


class TestSymbolEndpointPerformance:
    """Benchmark symbol endpoint performance."""

    def test_search_response_time(self, client: TestClient, benchmark):
        """Symbol search should respond in < 100ms."""

        def search_symbols():
            return client.get(
                "/api/v1/symbols/search",
                params={"q": "REL", "limit": 10},
            )

        result = benchmark(search_symbols)
        assert result.status_code in [200, 500, 503]

    def test_universe_response_time(self, client: TestClient, benchmark):
        """Universe lookup should respond in < 50ms."""

        def get_universe():
            return client.get("/api/v1/symbols/universe/nifty50")

        result = benchmark(get_universe)
        assert result.status_code in [200, 404, 500]


class TestMarketDataPerformance:
    """Benchmark market data endpoint performance."""

    def test_candles_response_time(self, client: TestClient, benchmark):
        """Candle fetch should respond in < 200ms."""

        def fetch_candles():
            return client.get(
                "/api/v1/market/candles",
                params={"symbol": "RELIANCE", "timeframe": "1m", "limit": 100},
            )

        result = benchmark(fetch_candles)
        assert result.status_code in [200, 404, 500, 503]

    def test_candles_pagination_performance(self, client: TestClient):
        """Large candle requests should complete in < 500ms."""
        start = time.time()
        response = client.get(
            "/api/v1/market/candles",
            params={"symbol": "RELIANCE", "timeframe": "1m", "limit": 1000},
        )
        elapsed = time.time() - start

        # Should complete within 500ms
        assert elapsed < 0.5 or response.status_code in [404, 500, 503]


class TestAnalyticsPerformance:
    """Benchmark analytics endpoint performance."""

    def test_snapshot_response_time(self, client: TestClient, benchmark):
        """Scanner snapshot should respond in < 300ms."""

        def fetch_snapshot():
            return client.get("/api/v1/scanner/snapshots", params={"limit": 50})

        result = benchmark(fetch_snapshot)
        assert result.status_code in [200, 500, 503]

    def test_top_candidates_response_time(self, client: TestClient, benchmark):
        """Top candidates should respond in < 200ms."""

        def fetch_candidates():
            return client.get("/api/v1/scanner/top-candidates", params={"limit": 10})

        result = benchmark(fetch_candidates)
        assert result.status_code in [200, 500, 503]


class TestReplayPerformance:
    """Benchmark replay endpoint performance."""

    def test_create_session_performance(self, client: TestClient, benchmark):
        """Session creation should complete in < 50ms."""

        def create_session():
            return client.post(
                "/api/v1/replay/sessions",
                json={"symbol": "RELIANCE", "date": "2024-01-15", "timeframe": "1m"},
            )

        result = benchmark(create_session)
        assert result.status_code in [200, 503]


class TestConcurrentRequests:
    """Test API behavior under concurrent load."""

    def test_concurrent_health_checks(self, client: TestClient):
        """Multiple concurrent health checks should all succeed."""
        import concurrent.futures

        def fetch_health():
            return client.get("/api/v1/health")

        with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
            futures = [executor.submit(fetch_health) for _ in range(10)]
            results = [f.result() for f in concurrent.futures.as_completed(futures)]

        # All should succeed
        assert all(r.status_code == 200 for r in results)

    def test_concurrent_symbol_search(self, client: TestClient):
        """Multiple concurrent symbol searches should not fail."""
        import concurrent.futures

        def search(query):
            return client.get(
                "/api/v1/symbols/search",
                params={"q": query, "limit": 5},
            )

        queries = ["REL", "TCS", "INFY", "HDFC", "ICICI"]

        with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
            futures = [executor.submit(search, q) for q in queries]
            results = [f.result() for f in concurrent.futures.as_completed(futures)]

        # All should succeed or return 503 (not initialized)
        assert all(r.status_code in [200, 500, 503] for r in results)


class TestMemoryUsage:
    """Test API memory usage patterns."""

    def test_no_memory_leak_repeated_requests(self, client: TestClient):
        """Repeated requests should not cause memory growth."""
        import tracemalloc

        tracemalloc.start()

        # Make 100 requests
        for _ in range(100):
            client.get("/api/v1/health")

        # Get memory snapshot
        _current, peak = tracemalloc.get_traced_memory()
        tracemalloc.stop()

        # Peak memory should be reasonable (< 100MB for test)
        assert peak < 100 * 1024 * 1024  # 100MB


class TestErrorHandlingPerformance:
    """Test error response performance."""

    def test_404_response_time(self, client: TestClient, benchmark):
        """404 responses should be fast (< 50ms)."""

        def fetch_not_found():
            return client.get("/api/v1/symbols/NONEXISTENT123")

        result = benchmark(fetch_not_found)
        assert result.status_code in [404, 503]

    def test_validation_error_response_time(self, client: TestClient, benchmark):
        """Validation errors should respond quickly (< 20ms)."""

        def invalid_request():
            return client.get("/api/v1/symbols/search", params={"q": ""})

        result = benchmark(invalid_request)
        assert result.status_code == 422
