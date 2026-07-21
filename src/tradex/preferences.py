"""CLI-only preferences store — NOT the AppConfig runtime schema.

Holds CLI UX state only: which broker is the default target, preferred
output format. Broker credentials and everything AppConfig governs stay in
``.env.*`` / ``src/config/schema.py``; this module never reads or writes
those (keeps the single-config-source invariant, see context/architecture.md
G4).
"""

from __future__ import annotations

import json
import os
from pathlib import Path

_ENV_OVERRIDE = "TRADEX_CLI_CONFIG_PATH"
_DEFAULT_PATH = Path.home() / ".tradex" / "cli.json"

_DEFAULTS: dict[str, str] = {"broker.default": "paper", "output.format": "human"}


class PreferencesStore:
    """JSON-file-backed key/value store for CLI preferences."""

    def __init__(self, path: Path | None = None):
        if path is not None:
            self._path = path
        elif os.environ.get(_ENV_OVERRIDE):
            self._path = Path(os.environ[_ENV_OVERRIDE])
        else:
            self._path = _DEFAULT_PATH

    def path(self) -> Path:
        return self._path

    def load(self) -> dict[str, str]:
        if not self._path.exists():
            return dict(_DEFAULTS)
        try:
            data = json.loads(self._path.read_text())
        except (json.JSONDecodeError, OSError):
            return dict(_DEFAULTS)
        return {**_DEFAULTS, **{k: v for k, v in data.items() if k in _DEFAULTS}}

    def save(self, prefs: dict[str, str]) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._path.write_text(json.dumps(prefs, indent=2))

    def get(self, key: str) -> str:
        if key not in _DEFAULTS:
            raise KeyError(f"unknown config key {key!r} (known: {sorted(_DEFAULTS)})")
        return self.load()[key]

    def set(self, key: str, value: str) -> dict[str, str]:
        if key not in _DEFAULTS:
            raise KeyError(f"unknown config key {key!r} (known: {sorted(_DEFAULTS)})")
        prefs = self.load()
        prefs[key] = value
        self.save(prefs)
        return prefs

    def reset(self) -> dict[str, str]:
        prefs = dict(_DEFAULTS)
        self.save(prefs)
        return prefs
