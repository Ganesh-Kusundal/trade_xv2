"""Unit tests for tradex CLI preferences store."""

from __future__ import annotations

import pytest

from tradex.preferences import PreferencesStore


def test_defaults(tmp_path) -> None:
    store = PreferencesStore(path=tmp_path / "cli.json")
    assert store.get("broker.default") == "paper"
    assert store.get("output.format") == "human"


def test_set_and_get(tmp_path) -> None:
    store = PreferencesStore(path=tmp_path / "cli.json")
    store.set("broker.default", "dhan")
    assert store.get("broker.default") == "dhan"
    assert PreferencesStore(path=tmp_path / "cli.json").get("broker.default") == "dhan"


def test_unknown_key_raises(tmp_path) -> None:
    store = PreferencesStore(path=tmp_path / "cli.json")
    with pytest.raises(KeyError):
        store.get("nope")


def test_reset(tmp_path) -> None:
    store = PreferencesStore(path=tmp_path / "cli.json")
    store.set("broker.default", "upstox")
    store.reset()
    assert store.get("broker.default") == "paper"


def test_env_override(tmp_path, monkeypatch) -> None:
    path = tmp_path / "override.json"
    monkeypatch.setenv("TRADEX_CLI_CONFIG_PATH", str(path))
    store = PreferencesStore()
    store.set("broker.default", "dhan")
    assert PreferencesStore().get("broker.default") == "dhan"
    monkeypatch.delenv("TRADEX_CLI_CONFIG_PATH", raising=False)
