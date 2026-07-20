"""CLI smoke tests for the broker developer CLI."""

from __future__ import annotations

import pytest
from click.testing import CliRunner

from brokers.cli.broker import broker


@pytest.mark.unit
@pytest.mark.certification
def test_cli_order_and_security_paper(monkeypatch) -> None:
    monkeypatch.setattr(
        "brokers.cli.broker.get_quote",
        lambda b, symbol: {"symbol": symbol, "ltp": 123.0},
    )
    runner = CliRunner()
    r1 = runner.invoke(broker, ["--json", "--broker", "paper", "security", "RELIANCE"])
    assert r1.exit_code == 0, r1.output
    r2 = runner.invoke(broker, ["--json", "--broker", "paper", "quote", "RELIANCE"])
    assert r2.exit_code == 0, r2.output


@pytest.mark.unit
@pytest.mark.certification
def test_cli_discover(caplog) -> None:
    with caplog.at_level("INFO", logger="brokers.cli._render"):
        runner = CliRunner()
        result = runner.invoke(broker, ["--json", "discover"])
    assert result.exit_code == 0
    assert "paper" in caplog.text


@pytest.mark.unit
@pytest.mark.certification
def test_cli_verify_paper() -> None:
    runner = CliRunner()
    result = runner.invoke(broker, ["--broker", "paper", "verify"])
    assert result.exit_code == 0, result.output


@pytest.mark.unit
@pytest.mark.certification
def test_cli_quote_paper() -> None:
    runner = CliRunner()
    result = runner.invoke(broker, ["--broker", "paper", "quote", "RELIANCE"])
    assert result.exit_code == 0, result.output
