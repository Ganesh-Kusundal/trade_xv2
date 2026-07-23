"""Interface layer — consolidated smoke tests.

Tests FastAPI health, CLI structure, and TUI render.
"""

from __future__ import annotations


# ── FastAPI health endpoint ──────────────────────────────────────────


class TestHealthAPI:
    """Health endpoint contract."""

    def test_health_live_returns_200(self) -> None:
        from interface.api.health import create_app
        from fastapi.testclient import TestClient

        app = create_app()
        resp = TestClient(app).get("/health/live")
        assert resp.status_code == 200

    def test_health_live_returns_status_ok(self) -> None:
        from interface.api.health import create_app
        from fastapi.testclient import TestClient

        app = create_app()
        resp = TestClient(app).get("/health/live")
        body = resp.json()
        assert body["status"] == "ok"

    def test_health_ready_returns_200(self) -> None:
        from interface.api.health import create_app
        from fastapi.testclient import TestClient

        app = create_app()
        resp = TestClient(app).get("/health/ready")
        assert resp.status_code == 200

    def test_health_ready_returns_status_ok(self) -> None:
        from interface.api.health import create_app
        from fastapi.testclient import TestClient

        app = create_app()
        resp = TestClient(app).get("/health/ready")
        body = resp.json()
        assert body["status"] == "ok"


# ── CLI structure ─────────────────────────────────────────────────────


class TestCLIStructure:
    """CLI entry points exist and respond to basic commands."""

    def test_cli_main_callable(self) -> None:
        from interface.cli import main

        assert callable(main)

    def test_cli_version_returns_0(self) -> None:
        from interface.cli import main

        code = main(["version"])
        assert code == 0

    def test_cli_has_replay_command(self) -> None:
        from interface.cli import build_parser

        sub = build_parser()._subparsers._group_actions[0]
        assert "replay" in sub._name_parser_map

    def test_cli_has_backtest_command(self) -> None:
        from interface.cli import build_parser

        sub = build_parser()._subparsers._group_actions[0]
        assert "backtest" in sub._name_parser_map

    def test_cli_has_paper_command(self) -> None:
        from interface.cli import build_parser

        sub = build_parser()._subparsers._group_actions[0]
        assert "paper" in sub._name_parser_map


# ── TUI ───────────────────────────────────────────────────────────────


class TestTUI:
    """Minimal TUI smoke test."""

    def test_tui_renders(self) -> None:
        from interface.tui.app import TradeXTUI

        text = TradeXTUI().render()
        assert isinstance(text, str)
        assert text.strip()
