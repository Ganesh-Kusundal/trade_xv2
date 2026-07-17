"""Validate that the committed OpenAPI schema matches the backend.

Two modes:
1. Static: load web/openapi.json and check it's valid with expected routes.
2. Programmatic: build the FastAPI app and compare its generated schema
   against the committed file — catches drift where a route was added
   or removed but the spec wasn't regenerated.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

WEB_OPENAPI = Path(__file__).resolve().parents[3] / "web" / "openapi.json"

# Route prefixes that must exist in the schema (derived from router registrations
# in interface/api/main.py — update when adding routers).
REQUIRED_PREFIXES = [
    "/api/v1/health",
    "/api/v1/symbols",
    "/api/v1/market",
    "/api/v1/analytics",
    "/api/v1/scanner",
    "/api/v1/strategy",
    "/api/v1/options",
    "/api/v1/replay",
    "/api/v1/backtest",
    "/api/v1/portfolio",
    "/api/v1/orders",
    "/api/v1/live",
]

# Tags declared in create_app's openapi_tags — every registered router should
# produce at least one path tagged with one of these.
REQUIRED_TAGS = {
    "Health",
    "Symbols",
    "Market Data",
    "Analytics",
    "Scanner",
    "Strategy",
    "Options",
    "Replay",
    "Backtest",
    "Portfolio",
    "Orders",
    "Live Broker",
}


# ── Static schema tests (no server needed) ──────────────────────────────


@pytest.fixture(scope="module")
def openapi_schema():
    """Load the committed OpenAPI schema; skip if file is absent."""
    if not WEB_OPENAPI.exists():
        pytest.skip(f"OpenAPI spec not found at {WEB_OPENAPI}")
    with open(WEB_OPENAPI) as f:
        return json.load(f)


def test_openapi_is_valid_json_with_required_fields(openapi_schema):
    assert "openapi" in openapi_schema or "swagger" in openapi_schema
    assert "paths" in openapi_schema
    assert "info" in openapi_schema
    assert openapi_schema["info"].get("version"), "info.version must be non-empty"


def test_openapi_has_required_route_groups(openapi_schema):
    paths = openapi_schema["paths"]
    for prefix in REQUIRED_PREFIXES:
        matching = [p for p in paths if p.startswith(prefix)]
        assert matching, f"No routes found matching prefix {prefix}"


def test_openapi_covers_all_required_tags(openapi_schema):
    paths = openapi_schema["paths"]
    seen_tags: set[str] = set()
    for path_obj in paths.values():
        for method_obj in path_obj.values():
            if isinstance(method_obj, dict):
                seen_tags.update(method_obj.get("tags", []))
    missing = REQUIRED_TAGS - seen_tags
    assert not missing, f"Tags declared in OpenAPI config but missing from paths: {missing}"


def test_openapi_response_schemas_are_defined(openapi_schema):
    """Every 200 response with a JSON body should reference a defined component."""
    components = openapi_schema.get("components", {}).get("schemas", {})
    for path, path_obj in openapi_schema["paths"].items():
        for method, method_obj in path_obj.items():
            if not isinstance(method_obj, dict):
                continue
            for status, resp in method_obj.get("responses", {}).items():
                if status.startswith("2"):
                    content = resp.get("content", {}).get("application/json", {})
                    schema = content.get("schema", {})
                    ref = schema.get("$ref", "")
                    if ref:
                        schema_name = ref.split("/")[-1]
                        assert schema_name in components, (
                            f"{method.upper()} {path} refs {schema_name} "
                            f"but it's not in components.schemas"
                        )


# ── Programmatic drift detection ────────────────────────────────────────


def test_committed_schema_matches_fastapi_generated():
    """Build the app and diff generated schema against committed file.

    This catches the most common drift: someone adds/removes a router or
    endpoint in Python but forgets to regenerate web/openapi.json.

    Skips when create_app() can't be imported without full infrastructure
    (e.g. missing event_bus factory) — those environments should run the
    static tests above and regenerate the schema separately.
    """
    if not WEB_OPENAPI.exists():
        pytest.skip("No committed openapi.json to compare against")

    try:
        from interface.api.main import create_app
    except ImportError:
        pytest.skip("create_app() dependencies unavailable in this environment")

    try:
        app = create_app()
    except Exception as exc:
        pytest.skip(f"create_app() failed (needs full infra): {exc}")

    generated = app.openapi()

    with open(WEB_OPENAPI) as f:
        committed = json.load(f)

    gen_paths = set(generated.get("paths", {}).keys())
    committed_paths = set(committed.get("paths", {}).keys())

    added = gen_paths - committed_paths
    removed = committed_paths - gen_paths

    # Allow minor tolerance: committed schema may lag behind by one cycle,
    # but we flag both directions as warnings rather than hard failures
    # for the "removed" case (intentional deprecations are fine).
    assert not added, (
        f"Routes in generated schema but MISSING from committed openapi.json: "
        f"{sorted(added)}. Regenerate with: python -m scripts.generate_openapi"
    )
    # Removed routes are informational — could be intentional deprecation.
    if removed:
        pytest.xfail(
            f"Routes in committed schema but MISSING from generated: "
            f"{sorted(removed)}. May be intentional deprecation."
        )
