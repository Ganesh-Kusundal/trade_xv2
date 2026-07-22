"""Load .env.local into os.environ (stdlib — no python-dotenv required)."""

from __future__ import annotations

import os
from pathlib import Path


def load_env_file(path: str | Path, *, override: bool = True) -> Path | None:
    """Parse KEY=VALUE lines into os.environ. Returns path if loaded."""
    p = Path(path)
    if not p.is_file():
        return None
    for raw in p.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if not key:
            continue
        if override or key not in os.environ:
            os.environ[key] = value
    return p


def load_v2_env(*, override: bool = True) -> Path | None:
    """Load v2/.env.local (fallback: repo-root .env.local)."""
    # shared/env.py → parents[2] = v2/
    v2_root = Path(__file__).resolve().parents[2]
    repo_root = v2_root.parent
    loaded = load_env_file(v2_root / ".env.local", override=override)
    if loaded is None:
        loaded = load_env_file(repo_root / ".env.local", override=override)
    # Legacy Upstox aliases from .env.local — API_KEY is the OAuth client_id for TOTP apps
    if os.environ.get("UPSTOX_API_KEY"):
        os.environ["UPSTOX_CLIENT_ID"] = os.environ["UPSTOX_API_KEY"]
    if os.environ.get("UPSTOX_API_SECRET"):
        os.environ["UPSTOX_CLIENT_SECRET"] = os.environ["UPSTOX_API_SECRET"]
    return loaded
