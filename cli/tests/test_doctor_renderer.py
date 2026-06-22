"""Unit tests for ResultRenderer.

Tests table formatting, status color coding, and summary rendering.

Phase P4-2 (2026-06-22): Renderer TDD tests.
"""

from __future__ import annotations

import pytest
from rich.console import Console

from cli.commands.doctor.checks import CheckResult
from cli.commands.doctor.renderer import ResultRenderer, _status_str


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def console():
    """Return a Rich console with recording enabled."""
    return Console(record=True)


@pytest.fixture()
def renderer(console):
    """Return a ResultRenderer instance."""
    return ResultRenderer(console)


# ---------------------------------------------------------------------------
# Test _status_str
# ---------------------------------------------------------------------------


class TestStatusStr:
    """Tests for _status_str helper function."""

    def test_pass_status(self):
        result = _status_str("PASS")
        assert "green" in result
        assert "PASS" in result

    def test_warn_status(self):
        result = _status_str("WARN")
        assert "yellow" in result
        assert "WARN" in result

    def test_fail_status(self):
        result = _status_str("FAIL")
        assert "red" in result
        assert "FAIL" in result

    def test_info_status(self):
        result = _status_str("INFO")
        assert "dim" in result
        assert "INFO" in result

    def test_error_status(self):
        result = _status_str("ERROR")
        assert "red" in result
        assert "ERROR" in result

    def test_unknown_status(self):
        result = _status_str("UNKNOWN")
        assert "red" in result
        assert "FAIL" in result  # Defaults to FAIL


# ---------------------------------------------------------------------------
# Test ResultRenderer
# ---------------------------------------------------------------------------


class TestResultRenderer:
    """Tests for ResultRenderer."""

    def test_render_section_with_results(self, renderer, console):
        """Test rendering a section with results."""
        results = [
            CheckResult("Check1", "PASS", "OK"),
            CheckResult("Check2", "FAIL", "Error"),
        ]
        renderer.render_section("Test Section", results)
        
        output = console.export_text()
        assert "Test Section" in output
        assert "Check1" in output
        assert "Check2" in output

    def test_render_section_empty(self, renderer, console):
        """Test that empty sections are not rendered."""
        renderer.render_section("Empty Section", [])
        
        output = console.export_text()
        assert "Empty Section" not in output

    def test_render_section_no_header(self, renderer, console):
        """Test rendering without column headers."""
        results = [CheckResult("Check1", "PASS")]
        renderer.render_section("No Header", results, show_header=False)
        
        output = console.export_text()
        # Should still render but without headers
        assert "No Header" in output

    def test_render_sections_multiple(self, renderer, console):
        """Test rendering multiple sections."""
        sections = [
            ("Section1", [CheckResult("Check1", "PASS")]),
            ("Section2", [CheckResult("Check2", "WARN")]),
        ]
        renderer.render_sections(sections)
        
        output = console.export_text()
        assert "Section1" in output
        assert "Section2" in output

    def test_render_summary_all_pass(self, renderer, console):
        """Test summary with all passing checks."""
        results = [
            CheckResult("Check1", "PASS"),
            CheckResult("Check2", "PASS"),
        ]
        renderer.render_summary(results)
        
        output = console.export_text()
        assert "Summary:" in output
        assert "2 passed" in output

    def test_render_summary_mixed(self, renderer, console):
        """Test summary with mixed results."""
        results = [
            CheckResult("Check1", "PASS"),
            CheckResult("Check2", "WARN"),
            CheckResult("Check3", "FAIL"),
            CheckResult("Check4", "INFO"),
        ]
        renderer.render_summary(results)
        
        output = console.export_text()
        assert "1 passed" in output
        assert "1 warnings" in output
        assert "1 failed" in output
        assert "1 info" in output

    def test_render_summary_with_errors(self, renderer, console):
        """Test summary with ERROR status."""
        results = [
            CheckResult("Check1", "ERROR", "Exception"),
        ]
        renderer.render_summary(results)
        
        output = console.export_text()
        assert "1 error" in output

    def test_render_summary_empty(self, renderer, console):
        """Test summary with no results."""
        renderer.render_summary([])
        
        output = console.export_text()
        assert "Summary:" in output
        assert "0 checks total" in output
