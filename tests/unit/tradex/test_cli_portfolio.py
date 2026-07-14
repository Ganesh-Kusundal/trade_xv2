"""Tests for `tradex portfolio`."""

from __future__ import annotations

import pytest
from click.testing import CliRunner

from tradex.cli import tradex


@pytest.mark.unit
def test_portfolio_show_paper_runs_clean() -> None:
    result = CliRunner().invoke(tradex, ["portfolio", "--broker", "paper", "show"])
    assert result.exit_code == 0, result.output


@pytest.mark.unit
def test_portfolio_holdings_paper_runs_clean() -> None:
    result = CliRunner().invoke(tradex, ["portfolio", "--broker", "paper", "holdings"])
    assert result.exit_code == 0, result.output


@pytest.mark.unit
def test_portfolio_funds_paper_runs_clean() -> None:
    result = CliRunner().invoke(tradex, ["portfolio", "--broker", "paper", "funds"])
    assert result.exit_code == 0, result.output
