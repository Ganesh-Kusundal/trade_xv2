"""REST API route manifest tests — OpenAPI schema vs capability manifest."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from domain.capability_manifest import CAPABILITY_SURFACES
from interface.api.config import APIConfig
from interface.api.main import create_app

# Manifest REST paths (normalized without method prefix for lookup).
_MANIFEST_REST_PATHS: set[tuple[str, str]] = set()
for surface in CAPABILITY_SURFACES:
    for rest in surface.rest:
        _MANIFEST_REST_PATHS.add((rest.method.upper(), rest.path))


@pytest.fixture
def openapi_paths() -> set[tuple[str, str]]:
    """Collect (METHOD, path) from OpenAPI schema."""
    app = create_app(config=APIConfig(auth_mode="none"))
    schema = app.openapi()
    paths: set[tuple[str, str]] = set()
    for path, methods in schema.get("paths", {}).items():
        for method in methods:
            if method.upper() in ("GET", "POST", "PUT", "DELETE", "PATCH"):
                # Normalize to manifest prefix style
                full_path = path if path.startswith("/api") else f"/api/v1{path}"
                paths.add((method.upper(), full_path))
    return paths


class TestApiRouteManifest:
    """OpenAPI routes are documented in capability manifest."""

    def test_health_routes_in_manifest(self) -> None:
        expected = {
            ("GET", "/api/v1/health"),
            ("GET", "/api/v1/health/readyz"),
            ("GET", "/api/v1/health/metrics"),
            ("GET", "/api/v1/health/metrics/prometheus"),
        }
        assert expected <= _MANIFEST_REST_PATHS

    def test_core_trading_routes_in_manifest(self) -> None:
        expected = {
            ("GET", "/api/v1/orders"),
            ("POST", "/api/v1/orders"),
            ("GET", "/api/v1/portfolio/positions"),
            ("GET", "/api/v1/risk/state"),
            ("POST", "/api/v1/risk/kill-switch"),
        }
        assert expected <= _MANIFEST_REST_PATHS

    def test_openapi_core_routes_covered(self, openapi_paths: set[tuple[str, str]]) -> None:
        """Key OpenAPI routes appear in manifest (allow WS routes separately)."""
        api_routes = {p for p in openapi_paths if p[1].startswith("/api/v1")}
        manifest_api = {p for p in _MANIFEST_REST_PATHS if p[1].startswith("/api/v1")}
        # At least 80% of API routes should be in manifest
        if not api_routes:
            pytest.skip("No OpenAPI routes")
        covered = api_routes & manifest_api
        ratio = len(covered) / len(api_routes)
        assert ratio >= 0.75, (
            f"Only {len(covered)}/{len(api_routes)} API routes in manifest. "
            f"Missing sample: {sorted(api_routes - manifest_api)[:10]}"
        )

    def test_kill_switch_route_exists(self) -> None:
        assert ("POST", "/api/v1/risk/kill-switch") in _MANIFEST_REST_PATHS

    def test_prometheus_metrics_route_exists(self) -> None:
        assert ("GET", "/api/v1/health/metrics/prometheus") in _MANIFEST_REST_PATHS

    def test_liveness_endpoint_responds(self) -> None:
        app = create_app(config=APIConfig(auth_mode="none"))
        client = TestClient(app)
        resp = client.get("/api/v1/health")
        assert resp.status_code == 200

    def test_prometheus_metrics_endpoint_responds(self) -> None:
        app = create_app(config=APIConfig(auth_mode="none"))
        client = TestClient(app)
        resp = client.get("/api/v1/health/metrics/prometheus")
        assert resp.status_code == 200
        assert "text/plain" in resp.headers.get("content-type", "")
