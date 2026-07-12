"""Tests for the unified ``tradex`` dispatcher CLI.

Verifies the facade wires up the existing broker group and exposes the UI
command, without reimplementing either backend.
"""

from __future__ import annotations

import pytest
from click.testing import CliRunner

from tradex.cli import tradex


@pytest.mark.unit
def test_tradex_help_lists_subcommands() -> None:
    runner = CliRunner()
    result = runner.invoke(tradex, ["--help"])
    assert result.exit_code == 0, result.output
    assert "broker" in result.output
    assert "ui" in result.output


@pytest.mark.unit
def test_tradex_broker_help_shows_subcommands() -> None:
    runner = CliRunner()
    result = runner.invoke(tradex, ["broker", "--help"])
    assert result.exit_code == 0, result.output
    # The delegated broker group exposes its own commands (e.g. discover).
    assert "discover" in result.output


@pytest.mark.unit
def test_tradex_version_option() -> None:
    runner = CliRunner()
    result = runner.invoke(tradex, ["--version"])
    assert result.exit_code == 0, result.output
    assert "0.1.0" in result.output
