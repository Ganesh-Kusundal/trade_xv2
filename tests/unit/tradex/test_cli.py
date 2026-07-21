"""Tests for the unified ``tradex`` dispatcher CLI."""

from __future__ import annotations

import pytest
from click.testing import CliRunner

from tradex.cli import tradex


@pytest.mark.unit
def test_tradex_help_lists_subcommands() -> None:
    runner = CliRunner()
    result = runner.invoke(tradex, ["--help"])
    assert result.exit_code == 0, result.output
    assert "ui" in result.output
    assert "config" in result.output
    assert "\n  broker " not in result.output and "\n  broker\n" not in result.output


@pytest.mark.unit
def test_tradex_no_broker_subcommand() -> None:
    runner = CliRunner()
    result = runner.invoke(tradex, ["broker", "--help"])
    assert result.exit_code != 0


@pytest.mark.unit
def test_tradex_version_option() -> None:
    runner = CliRunner()
    result = runner.invoke(tradex, ["--version"])
    assert result.exit_code == 0, result.output
    assert "0.1.0" in result.output


@pytest.mark.unit
def test_ui_forwards_broker_flag(monkeypatch: pytest.MonkeyPatch) -> None:
    """``--broker`` must reach ui.main, not die as unknown Click option on ``ui``."""
    captured: list[list[str]] = []
    monkeypatch.setattr("tradex.cli._dispatch_ui", lambda argv: captured.append(list(argv)))
    runner = CliRunner()
    result = runner.invoke(tradex, ["ui", "quote", "RELIANCE", "--broker", "dhan"])
    assert result.exit_code == 0, result.output
    assert captured == [["quote", "RELIANCE", "--broker", "dhan"]]
