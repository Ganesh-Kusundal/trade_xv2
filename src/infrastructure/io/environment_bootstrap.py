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


def _env_file_for_broker(broker: str) -> str | None:
    """Return the env file path for *broker* from the BrokerPlugin registry."""
    from infrastructure.broker_plugin import ensure_core_plugins, get_broker_plugin

    ensure_core_plugins()
    plugin = get_broker_plugin(broker)
    return plugin.env_file if plugin is not None else None


def _is_live_broker(broker: str) -> bool:
    """Return True if *broker* is a live (non-paper) broker."""
    from infrastructure.broker_plugin import ensure_core_plugins, get_broker_plugin

    ensure_core_plugins()
    plugin = get_broker_plugin(broker)
    return plugin.is_live if plugin is not None else True


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

    for broker in brokers:
        if not _is_live_broker(broker):
            continue
        rel = _env_file_for_broker(broker)
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
