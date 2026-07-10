"""Tests for --verbose and --timing CLI flags."""

from __future__ import annotations

import logging
from unittest.mock import patch

import pytest

from interface.ui.main import _parse_flags


class TestParseFlags:
    """Tests for _parse_flags function."""

    def test_default_flags(self):
        """Test default flag values."""
        broker, args, json_mode, verbose, show_timing = _parse_flags(["doctor"])
        assert broker == "dhan"
        assert args == ["doctor"]
        assert json_mode is False
        assert verbose is False
        assert show_timing is False

    def test_broker_flag(self):
        """Test --broker flag."""
        broker, args, _json_mode, _verbose, _show_timing = _parse_flags(
            ["--broker", "upstox", "doctor"]
        )
        assert broker == "upstox"
        assert args == ["doctor"]

    def test_json_flag(self):
        """Test --json flag."""
        _broker, args, json_mode, _verbose, _show_timing = _parse_flags(
            ["--json", "quote", "RELIANCE"]
        )
        assert json_mode is True
        assert args == ["quote", "RELIANCE"]

    def test_verbose_flag(self):
        """Test --verbose flag enables debug logging."""
        with patch.object(logging.getLogger(), "setLevel") as mock_set_level:
            _broker, _args, _json_mode, verbose, _show_timing = _parse_flags(["--verbose", "doctor"])
            assert verbose is True
            mock_set_level.assert_called_once_with(logging.DEBUG)

    def test_timing_flag(self):
        """Test --timing flag."""
        _broker, _args, _json_mode, _verbose, show_timing = _parse_flags(["--timing", "doctor"])
        assert show_timing is True

    def test_all_flags_together(self):
        """Test all flags together."""
        broker, args, json_mode, verbose, show_timing = _parse_flags(
            ["--broker", "upstox", "--json", "--verbose", "--timing", "doctor"]
        )
        assert broker == "upstox"
        assert args == ["doctor"]
        assert json_mode is True
        assert verbose is True
        assert show_timing is True

    def test_flags_in_any_order(self):
        """Test flags can appear in any order."""
        broker, args, _json_mode, verbose, show_timing = _parse_flags(
            ["doctor", "--timing", "--broker", "dhan", "--verbose"]
        )
        assert broker == "dhan"
        assert args == ["doctor"]
        assert verbose is True
        assert show_timing is True

    def test_multiple_commands_with_flags(self):
        """Test flags with multiple command arguments."""
        _broker, args, _json_mode, verbose, _show_timing = _parse_flags(
            ["--verbose", "place-order", "RELIANCE", "BUY", "10"]
        )
        assert verbose is True
        assert args == ["place-order", "RELIANCE", "BUY", "10"]

    def test_unknown_args_preserved(self):
        """Test unknown arguments are preserved in remaining args."""
        _broker, args, _json_mode, _verbose, _show_timing = _parse_flags(
            ["quote", "RELIANCE", "--unknown-flag"]
        )
        assert args == ["quote", "RELIANCE", "--unknown-flag"]


class TestVerboseFlag:
    """Tests for --verbose flag behavior."""

    def test_verbose_enables_debug_logging(self):
        """Test that --verbose sets logging level to DEBUG."""
        original_level = logging.getLogger().level

        try:
            with patch.object(logging.getLogger(), "setLevel") as mock_set_level:
                _parse_flags(["--verbose", "doctor"])
                mock_set_level.assert_called_once_with(logging.DEBUG)
        finally:
            # Restore original level
            logging.getLogger().setLevel(original_level)

    def test_verbose_does_not_affect_other_flags(self):
        """Test that --verbose doesn't change other flag defaults."""
        broker, _args, json_mode, _verbose, show_timing = _parse_flags(["--verbose", "doctor"])
        assert broker == "dhan"
        assert json_mode is False
        assert show_timing is False


class TestTimingFlag:
    """Tests for --timing flag behavior."""

    def test_timing_flag_sets_show_timing_true(self):
        """Test that --timing sets show_timing to True."""
        _broker, _args, _json_mode, _verbose, show_timing = _parse_flags(["--timing", "doctor"])
        assert show_timing is True

    def test_timing_does_not_affect_other_flags(self):
        """Test that --timing doesn't change other flag defaults."""
        broker, _args, json_mode, verbose, _show_timing = _parse_flags(["--timing", "doctor"])
        assert broker == "dhan"
        assert json_mode is False
        assert verbose is False


class TestFlagCombinations:
    """Tests for flag combinations."""

    @pytest.mark.parametrize(
        "flags,expected",
        [
            # (input_flags, (broker, json, verbose, timing))
            (["--json"], ("dhan", True, False, False)),
            (["--verbose"], ("dhan", False, True, False)),
            (["--timing"], ("dhan", False, False, True)),
            (["--json", "--verbose"], ("dhan", True, True, False)),
            (["--json", "--timing"], ("dhan", True, False, True)),
            (["--verbose", "--timing"], ("dhan", False, True, True)),
            (["--json", "--verbose", "--timing"], ("dhan", True, True, True)),
            (
                ["--broker", "upstox", "--json"],
                ("upstox", True, False, False),
            ),
            (
                ["--broker", "upstox", "--verbose", "--timing"],
                ("upstox", False, True, True),
            ),
        ],
    )
    def test_flag_combinations(self, flags, expected):
        """Test various flag combinations."""
        expected_broker, expected_json, expected_verbose, expected_timing = expected
        broker, args, json_mode, verbose, show_timing = _parse_flags([*flags, "doctor"])

        assert broker == expected_broker
        assert json_mode == expected_json
        assert verbose == expected_verbose
        assert show_timing == expected_timing
        assert args == ["doctor"]
