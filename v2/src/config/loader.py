"""Config loader: defaults → base YAML → profile → TRADEX_* env → overrides."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import yaml

from config.schema import AppConfig


def _deep_merge(base: dict[str, Any], overlay: dict[str, Any]) -> dict[str, Any]:
    out = dict(base)
    for key, val in overlay.items():
        if key in out and isinstance(out[key], dict) and isinstance(val, dict):
            out[key] = _deep_merge(out[key], val)
        else:
            out[key] = val
    return out


def _load_yaml(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    data = yaml.safe_load(path.read_text()) or {}
    if not isinstance(data, dict):
        msg = f"Config must be a mapping: {path}"
        raise ValueError(msg)
    return data


def _env_overrides() -> dict[str, Any]:
    """Map TRADEX_* env vars onto AppConfig field paths."""
    mapping = {
        "TRADEX_ENVIRONMENT": ("environment",),
        "TRADEX_BROKER": ("broker",),
        "TRADEX_LOGGING_LEVEL": ("logging", "level"),
    }
    out: dict[str, Any] = {}
    for env_key, path in mapping.items():
        raw = os.environ.get(env_key)
        if raw is None:
            continue
        cursor: dict[str, Any] = out
        for part in path[:-1]:
            cursor = cursor.setdefault(part, {})
        cursor[path[-1]] = raw
    return out


def load_config(
    config_dir: str | Path,
    profile: str,
    overrides: dict[str, Any] | None = None,
) -> AppConfig:
    root = Path(config_dir)
    # 1. Built-in defaults via AppConfig()
    merged: dict[str, Any] = AppConfig().model_dump(mode="json")
    # 2. Base YAML
    merged = _deep_merge(merged, _load_yaml(root / "tradex.yaml"))
    # 3. Profile overlay
    merged = _deep_merge(merged, _load_yaml(root / "profiles" / f"{profile}.yaml"))
    # 4. TRADEX_* environment
    merged = _deep_merge(merged, _env_overrides())
    # 5. Explicit overrides
    if overrides:
        merged = _deep_merge(merged, overrides)
    return AppConfig.model_validate(merged)
