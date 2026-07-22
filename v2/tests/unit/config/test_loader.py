"""Config loader hierarchy: defaults → YAML → profile → env → overrides."""

from pathlib import Path

import pytest

from config.loader import load_config


def test_profile_overlay_changes_environment(tmp_path: Path) -> None:
    config_dir = tmp_path / "config"
    profiles = config_dir / "profiles"
    profiles.mkdir(parents=True)
    (config_dir / "tradex.yaml").write_text("environment: PAPER\nbroker: paper\n")
    (profiles / "replay.yaml").write_text("environment: REPLAY\n")

    cfg = load_config(config_dir, profile="replay")
    assert cfg.environment == "REPLAY"


def test_env_tradex_broker_overrides(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    config_dir = tmp_path / "config"
    profiles = config_dir / "profiles"
    profiles.mkdir(parents=True)
    (config_dir / "tradex.yaml").write_text("environment: PAPER\nbroker: paper\n")
    (profiles / "paper.yaml").write_text("environment: PAPER\n")

    monkeypatch.setenv("TRADEX_BROKER", "dhan")
    cfg = load_config(config_dir, profile="paper")
    assert cfg.broker == "dhan"
