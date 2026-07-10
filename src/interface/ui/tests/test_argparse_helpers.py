"""Tests for cli.commands.argparse_helpers."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from rich.console import Console

from interface.ui.commands.argparse_helpers import parse_flag, require_symbol
from interface.ui.commands.registry import CommandResult


class TestParseFlag:
    def test_returns_value_when_flag_present(self) -> None:
        assert parse_flag(["--price", "150.00"], "--price") == "150.00"

    def test_returns_none_when_flag_absent(self) -> None:
        assert parse_flag(["--type", "LIMIT"], "--price") is None

    def test_returns_none_when_flag_is_last_arg(self) -> None:
        assert parse_flag(["--price"], "--price") is None

    def test_returns_value_among_multiple_flags(self) -> None:
        args = ["RELIANCE", "--type", "LIMIT", "--price", "150.00", "--exchange", "NSE"]
        assert parse_flag(args, "--type") == "LIMIT"
        assert parse_flag(args, "--price") == "150.00"
        assert parse_flag(args, "--exchange") == "NSE"

    def test_returns_none_for_empty_args(self) -> None:
        assert parse_flag([], "--price") is None

    def test_returns_first_occurrence(self) -> None:
        args = ["--price", "100", "--price", "200"]
        assert parse_flag(args, "--price") == "100"


class TestRequireSymbol:
    @pytest.fixture()
    def console(self) -> Console:
        return Console(record=True)

    @pytest.fixture()
    def broker_service(self) -> MagicMock:
        svc = MagicMock()
        svc.active_broker = MagicMock()
        return svc

    def test_returns_symbol_and_gateway(self, broker_service: MagicMock, console: Console) -> None:
        result = require_symbol(
            ["RELIANCE"], broker_service, console, usage="tradex quote <symbol>"
        )
        assert not isinstance(result, CommandResult)
        symbol, gw = result
        assert symbol == "RELIANCE"
        assert gw is broker_service.active_broker

    def test_returns_error_when_args_empty(self, broker_service: MagicMock, console: Console) -> None:
        result = require_symbol(
            [], broker_service, console, usage="tradex quote <symbol>"
        )
        assert isinstance(result, CommandResult)
        assert not result.success
        assert result.error == "Missing symbol"

    def test_returns_error_when_no_gateway(self, console: Console) -> None:
        svc = MagicMock()
        svc.active_broker = None
        result = require_symbol(
            ["RELIANCE"], svc, console, usage="tradex quote <symbol>"
        )
        assert isinstance(result, CommandResult)
        assert not result.success
        assert "No broker gateway" in result.error
