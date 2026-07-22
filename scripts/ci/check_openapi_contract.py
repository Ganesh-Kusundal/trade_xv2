#!/usr/bin/env python3
"""OpenAPI contract — committed web/openapi.json must match generated schema."""

from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
COMMITTED = ROOT / "web" / "openapi.json"


def _normalize_schema(raw: dict) -> dict:
    """Stable JSON round-trip for comparison (sorted keys, no whitespace drift)."""
    return json.loads(json.dumps(raw, sort_keys=True))


def main() -> int:
    if not COMMITTED.is_file():
        print(
            f"Missing committed OpenAPI spec: {COMMITTED}\n"
            "Run: python -m scripts.generate_openapi",
            file=sys.stderr,
        )
        return 1

    sys.path.insert(0, str(ROOT / "src"))
    sys.path.insert(0, str(ROOT))

    from scripts.generate_openapi import generate_openapi_schema

    try:
        generated = _normalize_schema(generate_openapi_schema())
    except Exception as exc:
        print(f"Failed to generate OpenAPI schema: {exc}", file=sys.stderr)
        return 1

    try:
        committed = _normalize_schema(json.loads(COMMITTED.read_text(encoding="utf-8")))
    except json.JSONDecodeError as exc:
        print(f"Committed OpenAPI spec is invalid JSON: {exc}", file=sys.stderr)
        return 1

    if generated == committed:
        path_count = len(generated.get("paths", {}))
        print(f"OK: web/openapi.json matches generated schema ({path_count} paths)")
        return 0

    gen_paths = set(generated.get("paths", {}))
    committed_paths = set(committed.get("paths", {}))
    added = sorted(gen_paths - committed_paths)
    removed = sorted(committed_paths - gen_paths)

    with tempfile.NamedTemporaryFile(
        mode="w",
        suffix=".json",
        delete=False,
        encoding="utf-8",
    ) as tmp:
        json.dump(generated, tmp, indent=2, sort_keys=True)
        tmp_path = tmp.name

    print("OpenAPI contract drift detected:", file=sys.stderr)
    if added:
        print(f"  routes in generated schema but missing from committed: {added}", file=sys.stderr)
    if removed:
        print(f"  routes in committed but missing from generated: {removed}", file=sys.stderr)
    if not added and not removed:
        print("  path sets match but schema bodies differ", file=sys.stderr)
    print(
        f"\nRegenerate with: python -m scripts.generate_openapi\n"
        f"Fresh schema written to: {tmp_path}",
        file=sys.stderr,
    )
    return 1


if __name__ == "__main__":
    sys.exit(main())
