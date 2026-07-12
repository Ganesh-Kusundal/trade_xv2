"""Unit tests for Rich broker shell header."""

from __future__ import annotations

from io import StringIO

from rich.console import Console

from brokers.cli._shell_ui import render_header


def test_render_header_connected() -> None:
    buf = StringIO()
    out = Console(file=buf, width=120, force_terminal=True)
    render_header({"mode": "sim", "orders_enabled": True, "connected": True}, "paper", out=out)
    text = buf.getvalue()
    assert "Trading OS Broker Shell" in text
    assert "paper" in text


def test_render_header_not_connected() -> None:
    buf = StringIO()
    out = Console(file=buf, width=120, force_terminal=True)
    render_header(
        {"connected": False, "remediation": "Check .env.local"},
        "dhan",
        out=out,
    )
    assert "not connected" in buf.getvalue()
