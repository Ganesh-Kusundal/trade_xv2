"""TOS-P4-002 — MCP tools expose platform_ops doctor/diagnose/certify/benchmark."""

from __future__ import annotations

from pathlib import Path

import pytest

TOOLS = Path(__file__).resolve().parents[2] / "src" / "brokers" / "mcp" / "tools.py"


@pytest.mark.architecture
def test_mcp_tools_include_platform_ops_surface() -> None:
    text = TOOLS.read_text(encoding="utf-8")
    for name in (
        "broker_doctor",
        "broker_diagnose",
        "broker_certify",
        "broker_verify",
        "broker_benchmark",
        "run_doctor",
        "run_diagnose",
        "run_certify",
        "run_benchmark",
    ):
        assert name in text, f"MCP missing platform_ops tool/import: {name}"
