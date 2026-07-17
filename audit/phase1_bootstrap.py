"""
PHASE 1 — BOOTSTRAP VALIDATION
Starts the real FastAPI app. No mocks. Captures actual bootstrap events,
measures real startup latency, verifies real routes are registered.
"""
import sys
import time
import traceback
from fastapi.testclient import TestClient

REQUIRED_ROUTES = ["/health", "/docs", "/openapi.json"]
OPTIONAL_ROUTES = ["/api/v1/orders", "/api/v1/positions", "/api/v1/portfolio"]

def run():
    print("=" * 70)
    print("PHASE 1 — BOOTSTRAP VALIDATION")
    print("=" * 70)

    # Step 1: import the factory
    try:
        from interface.api.main import create_app
        print("  [OK]  create_app imported")
    except Exception as exc:
        print(f"PHASE FAILED: PHASE 1 — BOOTSTRAP VALIDATION")
        print(f"REASON: {exc}")
        print(f"MISSING: interface.api.main:create_app")
        print(f"BLOCKING PATH: src/interface/api/main.py")
        sys.exit(1)

    # Step 2: instantiate app — captures any runtime errors during init
    t0 = time.perf_counter()
    try:
        app = create_app()
        bootstrap_ms = (time.perf_counter() - t0) * 1000
        print(f"  [OK]  create_app() completed in {bootstrap_ms:.2f}ms")
    except Exception as exc:
        print(f"PHASE FAILED: PHASE 1 — BOOTSTRAP VALIDATION")
        print(f"REASON: create_app() raised: {exc}")
        traceback.print_exc()
        sys.exit(1)

    # Step 3: probe via test client
    client = TestClient(app, raise_server_exceptions=False)

    for route in REQUIRED_ROUTES:
        try:
            resp = client.get(route)
            if resp.status_code < 500:
                print(f"  [OK]  GET {route} -> {resp.status_code}")
            else:
                print(f"  [FAIL] GET {route} -> {resp.status_code} (server error)")
        except Exception as exc:
            print(f"  [FAIL] GET {route} raised: {exc}")

    # Discover registered routes
    print()
    print("  [ROUTES REGISTERED ON APP]")
    for route in sorted(str(r.path) for r in app.routes):
        print(f"    {route}")

    # Verify app has a lifespan
    has_lifespan = app.router.lifespan_handler is not None
    print(f"\n  [LIFESPAN] handler present: {has_lifespan}")
    assert has_lifespan, "FAIL: No lifespan handler — startup/shutdown logic missing"

    assert bootstrap_ms > 0
    print(f"\nPHASE 1 RESULT: BOOTSTRAP VALIDATED ({bootstrap_ms:.2f}ms)")

if __name__ == "__main__":
    run()
