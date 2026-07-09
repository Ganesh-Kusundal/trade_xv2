"""Central environment bootstrap for all process entry points.

Loads canonical broker env files into ``os.environ``.  This is an
infrastructure concern — broker adapters implement credential resolution;
this module orchestrates the loading sequence.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path

logger = logging.getLogger(__name__)

# Canonical env file paths relative to project root.
# Moved here from tradex.runtime.auth.credential_resolver to break
# the infrastructure -> brokers dependency.
CANONICAL_ENV_FILES: dict[str, str] = {
    "dhan": ".env.local",
    "upstox": ".env.upstox",
}


def bootstrap_environment(
    project_root: Path | None = None,
    *,
    brokers: tuple[str, ...] = ("dhan", "upstox"),
) -> dict[str, Path | None]:
    """Load canonical broker env files into ``os.environ``.

    Returns a mapping of broker name to the path loaded (or ``None`` when
    missing or not configured). Safe to call multiple times (idempotent).
    """
    root = project_root or Path.cwd()
    loaded: dict[str, Path | None] = {}

    skip: set[str] = {"paper"}
    for broker in brokers:
        if broker in skip:
            continue
        rel = CANONICAL_ENV_FILES.get(broker)
        if rel is None:
            loaded[broker] = None
            continue
        path = root / rel
        if path.exists() and path.stat().st_size > 0:
            load_env_file(path)
            loaded[broker] = path
            logger.debug("bootstrap_environment: loaded %s from %s", broker, path)
        else:
            loaded[broker] = None

    return loaded


def load_env_file(path: Path) -> None:
    """Minimal .env parser — no python-dotenv dependency.

    Reads key=value pairs from the given file path and sets them
    as environment variables. Comments (lines starting with #) and
    blank lines are skipped. Values are stripped of surrounding quotes.

    This overwrites existing env vars so fresh tokens take effect.
    """
    if not path.exists():
        return
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        os.environ[key] = value
