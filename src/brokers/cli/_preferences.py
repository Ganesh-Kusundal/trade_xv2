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
from dataclasses import asdict, dataclass, replace
from pathlib import Path

_ENV_OVERRIDE = "TRADEX_CLI_CONFIG_PATH"
_DEFAULT_PATH = Path.home() / ".tradex" / "cli.json"

_KEY_FIELDS = {"broker.default": "broker_default", "output.format": "output_format"}


@dataclass(frozen=True)
class CliPreferences:
    broker_default: str = "paper"
    output_format: str = "human"

    def get(self, key: str) -> str:
        field = _KEY_FIELDS.get(key)
        if field is None:
            raise KeyError(f"unknown config key {key!r} (known: {sorted(_KEY_FIELDS)})")
        return getattr(self, field)

    def with_set(self, key: str, value: str) -> CliPreferences:
        field = _KEY_FIELDS.get(key)
        if field is None:
            raise KeyError(f"unknown config key {key!r} (known: {sorted(_KEY_FIELDS)})")
        return replace(self, **{field: value})

    def as_dict(self) -> dict[str, str]:
        data = asdict(self)
        return {key: data[field] for key, field in _KEY_FIELDS.items()}


class PreferencesStore:
    """JSON-file-backed store for :class:`CliPreferences`."""

    def __init__(self, path: Path | None = None):
        if path is not None:
            self._path = path
        elif os.environ.get(_ENV_OVERRIDE):
            self._path = Path(os.environ[_ENV_OVERRIDE])
        else:
            self._path = _DEFAULT_PATH

    def path(self) -> Path:
        return self._path

    def load(self) -> CliPreferences:
        if not self._path.exists():
            return CliPreferences()
        try:
            data = json.loads(self._path.read_text())
        except (json.JSONDecodeError, OSError):
            return CliPreferences()
        return CliPreferences(
            broker_default=data.get("broker.default", "paper"),
            output_format=data.get("output.format", "human"),
        )

    def save(self, prefs: CliPreferences) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._path.write_text(json.dumps(prefs.as_dict(), indent=2))

    def get(self, key: str) -> str:
        return self.load().get(key)

    def set(self, key: str, value: str) -> CliPreferences:
        prefs = self.load().with_set(key, value)
        self.save(prefs)
        return prefs

    def reset(self) -> CliPreferences:
        prefs = CliPreferences()
        self.save(prefs)
        return prefs
