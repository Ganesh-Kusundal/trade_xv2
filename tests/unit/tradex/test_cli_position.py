"""Tests for `tradex position list`."""

from __future__ import annotations

import pytest
from click.testing import CliRunner

from tradex.cli import tradex


@pytest.mark.unit
def test_position_list_paper_runs_clean() -> None:
    result = CliRunner().invoke(tradex, ["position", "--broker", "paper", "list"])
    assert result.exit_code == 0, result.output


@pytest.mark.unit
def test_position_list_uses_switched_default_broker(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("TRADEX_CLI_CONFIG_PATH", str(tmp_path / "cli.json"))
    from brokers.cli._preferences import PreferencesStore

    PreferencesStore().set("broker.default", "paper")
    result = CliRunner().invoke(tradex, ["position", "list"])
    assert result.exit_code == 0, result.output
