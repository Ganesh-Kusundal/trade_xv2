"""Unit tests for the CLI-only preferences store (not AppConfig)."""

from __future__ import annotations

import pytest

from brokers.cli._preferences import PreferencesStore


@pytest.mark.unit
def test_load_missing_file_returns_defaults(tmp_path) -> None:
    store = PreferencesStore(path=tmp_path / "cli.json")
    assert store.load() == {"broker.default": "paper", "output.format": "human"}


@pytest.mark.unit
def test_set_then_get_round_trips(tmp_path) -> None:
    store = PreferencesStore(path=tmp_path / "cli.json")
    store.set("broker.default", "dhan")
    assert store.get("broker.default") == "dhan"
    assert store.load()["broker.default"] == "dhan"


@pytest.mark.unit
def test_set_unknown_key_raises(tmp_path) -> None:
    store = PreferencesStore(path=tmp_path / "cli.json")
    with pytest.raises(KeyError):
        store.set("nope.nope", "x")


@pytest.mark.unit
def test_get_unknown_key_raises(tmp_path) -> None:
    store = PreferencesStore(path=tmp_path / "cli.json")
    with pytest.raises(KeyError):
        store.get("nope.nope")


@pytest.mark.unit
def test_reset_restores_defaults(tmp_path) -> None:
    store = PreferencesStore(path=tmp_path / "cli.json")
    store.set("broker.default", "upstox")
    store.reset()
    assert store.get("broker.default") == "paper"


@pytest.mark.unit
def test_save_creates_parent_directories(tmp_path) -> None:
    nested = tmp_path / "nested" / "dir" / "cli.json"
    store = PreferencesStore(path=nested)
    store.set("output.format", "json")
    assert nested.exists()


@pytest.mark.unit
def test_env_override_path(tmp_path, monkeypatch) -> None:
    target = tmp_path / "from_env.json"
    monkeypatch.setenv("TRADEX_CLI_CONFIG_PATH", str(target))
    store = PreferencesStore()
    store.set("broker.default", "dhan")
    assert target.exists()
    assert PreferencesStore().get("broker.default") == "dhan"


@pytest.mark.unit
def test_corrupt_file_falls_back_to_defaults(tmp_path) -> None:
    path = tmp_path / "cli.json"
    path.write_text("{not valid json")
    store = PreferencesStore(path=path)
    assert store.load() == {"broker.default": "paper", "output.format": "human"}
