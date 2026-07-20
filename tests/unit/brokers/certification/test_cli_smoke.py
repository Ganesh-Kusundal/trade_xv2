"""CLI smoke tests for the broker developer CLI."""

from __future__ import annotations

import pytest
from click.testing import CliRunner

from brokers.cli.broker import broker


@pytest.mark.unit
@pytest.mark.certification
def test_cli_order_and_security_paper() -> None:
    runner = CliRunner()
    r1 = runner.invoke(broker, ["--broker", "paper", "security", "RELIANCE"])
    assert r1.exit_code == 0, r1.output
    assert "NSE:RELIANCE" in r1.output
    r2 = runner.invoke(broker, ["--broker", "paper", "order", "RELIANCE", "1", "--price", "100"])
    assert r2.exit_code == 0, r2.output


@pytest.mark.unit
@pytest.mark.certification
def test_cli_discover() -> None:
    runner = CliRunner()
    result = runner.invoke(broker, ["discover"])
    assert result.exit_code == 0
    assert "paper" in result.output


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
