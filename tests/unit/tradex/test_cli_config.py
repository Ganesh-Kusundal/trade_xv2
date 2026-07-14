"""Tests for `tradex config` — CLI-only preferences, not AppConfig."""

from __future__ import annotations

import pytest
from click.testing import CliRunner

from tradex.cli import tradex


@pytest.fixture
def cli_config_env(tmp_path, monkeypatch):
    monkeypatch.setenv("TRADEX_CLI_CONFIG_PATH", str(tmp_path / "cli.json"))
    return tmp_path / "cli.json"


@pytest.mark.unit
def test_config_list_shows_defaults(cli_config_env) -> None:
    result = CliRunner().invoke(tradex, ["config", "list"])
    assert result.exit_code == 0, result.output
    assert "broker.default=paper" in result.output
    assert "output.format=human" in result.output


@pytest.mark.unit
def test_config_set_then_get(cli_config_env) -> None:
    runner = CliRunner()
    result = runner.invoke(tradex, ["config", "set", "broker.default", "dhan"])
    assert result.exit_code == 0, result.output
    result = runner.invoke(tradex, ["config", "get", "broker.default"])
    assert result.exit_code == 0, result.output
    assert result.output.strip() == "dhan"


@pytest.mark.unit
def test_config_set_unknown_key_fails(cli_config_env) -> None:
    result = CliRunner().invoke(tradex, ["config", "set", "nope.nope", "x"])
    assert result.exit_code != 0


@pytest.mark.unit
def test_config_get_unknown_key_fails(cli_config_env) -> None:
    result = CliRunner().invoke(tradex, ["config", "get", "nope.nope"])
    assert result.exit_code != 0


@pytest.mark.unit
def test_config_reset_prompts_and_restores_defaults(cli_config_env) -> None:
    runner = CliRunner()
    runner.invoke(tradex, ["config", "set", "broker.default", "upstox"])
    result = runner.invoke(tradex, ["config", "reset"], input="y\n")
    assert result.exit_code == 0, result.output
    result = runner.invoke(tradex, ["config", "get", "broker.default"])
    assert result.output.strip() == "paper"


@pytest.mark.unit
def test_config_reset_aborts_without_confirmation(cli_config_env) -> None:
    runner = CliRunner()
    runner.invoke(tradex, ["config", "set", "broker.default", "upstox"])
    result = runner.invoke(tradex, ["config", "reset"], input="n\n")
    assert result.exit_code != 0
    result = runner.invoke(tradex, ["config", "get", "broker.default"])
    assert result.output.strip() == "upstox"
