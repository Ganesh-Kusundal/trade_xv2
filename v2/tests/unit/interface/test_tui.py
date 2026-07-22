"""TUI — render returns non-empty status string."""

from __future__ import annotations

from interface.tui.app import TradeXTUI


def test_render_non_empty() -> None:
    text = TradeXTUI().render()
    assert isinstance(text, str)
    assert text.strip()
