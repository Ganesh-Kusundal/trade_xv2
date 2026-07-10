"""Backward-compat entry: ``python -m api`` → uvicorn on interface.api.main:create_app."""

from __future__ import annotations

import sys
from pathlib import Path

# Ensure src/ is importable when launched as python -m api from repo root.
_root = Path(__file__).resolve().parents[1]
_src = _root / "src"
if str(_src) not in sys.path:
    sys.path.insert(0, str(_src))


def main() -> None:
    import uvicorn

    from interface.api.main import create_app

    app = create_app()
    uvicorn.run(app, host="127.0.0.1", port=8080)


if __name__ == "__main__":
    main()
