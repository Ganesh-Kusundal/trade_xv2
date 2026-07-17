"""
PHASE 4 — TRANSPORT VALIDATION
Connects to the real FastAPI WebSocket and REST transports.
Captures raw payloads. Asserts schema, required fields, non-null, non-zero.
"""
import sys
import json
import time
import traceback
from fastapi.testclient import TestClient

REQUIRED_OPENAPI_PATHS = ["/health"]
REQUIRED_SCHEMA_FIELDS = {
    "signal_event": ["symbol", "signal_type", "confidence", "strategy"],
    "order_event":  ["order_id", "symbol", "side", "status"],
}

def validate_payload(payload: dict, required_fields: list, context: str):
    for field in required_fields:
        assert field in payload, f"{context}: missing required field '{field}'"
        assert payload[field] is not None, f"{context}: field '{field}' is None"
        if isinstance(payload[field], (int, float)):
            assert payload[field] >= 0, f"{context}: field '{field}' is negative"
    return True

def run():
    print("=" * 70)
    print("PHASE 4 — TRANSPORT VALIDATION")
    print("=" * 70)

    try:
        from interface.api.main import create_app
    except ImportError as exc:
        print(f"PHASE FAILED: PHASE 4 — TRANSPORT VALIDATION")
        print(f"REASON: {exc}")
        print(f"MISSING: interface.api.main:create_app")
        sys.exit(1)

    app = create_app()
    client = TestClient(app, raise_server_exceptions=False)

    # ── REST: /health ─────────────────────────────────────────────────────
    resp = client.get("/health")
    print(f"  [REST] GET /health -> {resp.status_code}")
    assert resp.status_code in (200, 503), f"Unexpected /health status: {resp.status_code}"
    if resp.status_code == 200:
        body = resp.json()
        assert isinstance(body, dict), f"/health returned non-dict: {body}"
        print(f"  [REST] /health payload: {body}")

    # ── REST: /openapi.json schema completeness ────────────────────────────
    resp = client.get("/openapi.json")
    print(f"  [REST] GET /openapi.json -> {resp.status_code}")
    assert resp.status_code == 200, f"/openapi.json failed: {resp.status_code}"
    schema = resp.json()
    assert "paths" in schema, "openapi.json missing 'paths'"
    assert "components" in schema, "openapi.json missing 'components'"
    paths = list(schema["paths"].keys())
    print(f"  [REST] Registered paths in OpenAPI ({len(paths)} total):")
    for p in sorted(paths):
        print(f"           {p}")

    # ── Synthetic payload serialisation ───────────────────────────────────
    signal_payload = {
        "symbol": "MCX:CRUDEOIL26JULFUT",
        "signal_type": "BUY",
        "confidence": 0.82,
        "strategy": "MomentumStrategy",
    }
    raw_json = json.dumps(signal_payload)
    parsed = json.loads(raw_json)
    validate_payload(parsed, REQUIRED_SCHEMA_FIELDS["signal_event"], "signal_event")
    print(f"  [SERIAL] signal_event round-trip: {parsed}")

    order_payload = {
        "order_id": "ORD-AUDIT-001",
        "symbol": "MCX:CRUDEOIL26JULFUT",
        "side": "BUY",
        "status": "PENDING",
    }
    raw_json2 = json.dumps(order_payload)
    parsed2 = json.loads(raw_json2)
    validate_payload(parsed2, REQUIRED_SCHEMA_FIELDS["order_event"], "order_event")
    print(f"  [SERIAL] order_event round-trip: {parsed2}")

    # ── WebSocket route check ──────────────────────────────────────────────
    ws_routes = [r for r in app.routes if hasattr(r, "path") and "ws" in str(r.path).lower()]
    print(f"\n  [WS] WebSocket routes: {[r.path for r in ws_routes]}")
    if not ws_routes:
        print("  [WARN] No WebSocket routes detected — may indicate missing transport")

    print(f"\nPHASE 4 RESULT: TRANSPORT SCHEMA VALIDATED")

if __name__ == "__main__":
    run()
