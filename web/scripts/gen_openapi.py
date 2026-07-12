"""Generate the API OpenAPI document from the FastAPI app.

The web TypeScript SDK is generated from this spec (see DR-F5 /
``openapi-typescript``). We build the app with no live services attached: for
OpenAPI generation we only need the routers mounted, not a running broker/DB,
so every service is passed as ``None`` and FastAPI introspects the signatures.

Usage:
    python scripts/gen_openapi.py            # writes ../openapi.json
    PYTHONPATH=../src python scripts/gen_openapi.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent  # web/scripts
WEB = ROOT.parent  # web
REPO = WEB.parent  # repo root

# Make the Python packages importable (src/ is the package root).
for p in (str(REPO / "src"), str(REPO)):
    if p not in sys.path:
        sys.path.insert(0, p)


def main() -> int:
    from interface.api.config import APIConfig
    from interface.api.main import create_app

    app = create_app(config=APIConfig())
    spec = app.openapi()

    out = WEB / "openapi.json"
    out.write_text(json.dumps(spec, indent=2, sort_keys=False), encoding="utf-8")
    paths = len(spec.get("paths", {}))
    print(f"Wrote {out} — {paths} paths, {len(spec.get('components', {}).get('schemas', {}))} schemas")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
