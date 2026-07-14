"""Unit tests for the new `tradex broker` identity commands: list/current/switch/status.

Content assertions on --json output go through caplog (present()'s json/yaml
branches write via logger.info(), not stdout directly — see the note in
test_cli_render.py::test_present_json_mode_when_piped and this file's
sibling commit for why CliRunner's res.output is unreliable for that
channel in this environment; caplog attaches directly to the logger and
sidesteps the issue).
"""

from __future__ import annotations

import json

import pytest
from click.testing import CliRunner

from brokers.cli.broker import broker


@pytest.fixture
def cli_config_env(tmp_path, monkeypatch):
    monkeypatch.setenv("TRADEX_CLI_CONFIG_PATH", str(tmp_path / "cli.json"))
    return tmp_path / "cli.json"


def _invoke_json(args: list[str], caplog):
    with caplog.at_level("INFO", logger="brokers.cli._render"):
        result = CliRunner().invoke(broker, ["--json", *args])
    assert result.exit_code == 0, result.output
    assert caplog.records, "no log record captured"
    return json.loads(caplog.records[-1].message)


@pytest.mark.unit
def test_broker_list_includes_paper_connected(cli_config_env, caplog) -> None:
    rows = _invoke_json(["list"], caplog)
    paper_rows = [r for r in rows if r["broker"] == "paper"]
    assert paper_rows, rows
    assert paper_rows[0]["connected"] is True
    assert paper_rows[0]["active"] is True  # paper is the default before any switch


@pytest.mark.unit
def test_broker_list_marks_configured_default_active(cli_config_env, caplog) -> None:
    from brokers.cli._preferences import PreferencesStore

    PreferencesStore().set("broker.default", "dhan")
    rows = _invoke_json(["list"], caplog)
    by_id = {r["broker"]: r for r in rows}
    assert by_id["paper"]["active"] is False
    if "dhan" in by_id:
        assert by_id["dhan"]["active"] is True
