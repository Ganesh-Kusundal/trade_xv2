"""Ensure production code uses bootstrap_gateway, not raw factory bypass paths."""

from __future__ import annotations

import re
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]

# Directories scanned for bypass patterns (production + verify scripts).
_SCAN_DIRS = (
    PROJECT_ROOT / "src" / "interface",
    PROJECT_ROOT / "src" / "application",
    PROJECT_ROOT / "src" / "runtime",
    PROJECT_ROOT / "scripts" / "verify",
    PROJECT_ROOT / "scripts" / "debug",
    PROJECT_ROOT / "scripts" / "migration",
    PROJECT_ROOT / "tests" / "integration" / "scripts",
)

# Files allowed to call private transport/factory APIs.
_ALLOWLIST = {
    PROJECT_ROOT / "src" / "infrastructure" / "gateway" / "factory.py",
    PROJECT_ROOT / "src" / "brokers" / "dhan" / "identity" / "factory.py",
    PROJECT_ROOT / "src" / "brokers" / "upstox" / "factory.py",
    PROJECT_ROOT / "src" / "runtime" / "broker_builders.py",
}

# Unit tests for factories may import BrokerFactory directly.
_ALLOWLIST_PREFIXES = (
    PROJECT_ROOT / "tests" / "unit" / "brokers",
    PROJECT_ROOT / "tests" / "architecture",
    PROJECT_ROOT / "tests" / "component" / "ui" / "test_broker_registry.py",
)

_FORBIDDEN_PATTERNS = (
    re.compile(r"BrokerFactory\s*\(\s*\)\s*\.\s*create\s*\("),
    re.compile(r"UpstoxBrokerFactory\s*\(\s*\)\s*\.\s*create\s*\("),
    re.compile(r"\bcreate_gateway\s*\("),
)

# Deprecated shim still exists; UI commands must not call it.
_UI_COMMANDS = PROJECT_ROOT / "src" / "interface" / "ui" / "commands"


def _is_allowlisted(path: Path) -> bool:
    resolved = path.resolve()
    if resolved in _ALLOWLIST:
        return True
    return any(str(resolved).startswith(str(prefix.resolve())) for prefix in _ALLOWLIST_PREFIXES)


def _iter_py_files(root: Path):
    if not root.exists():
        return
    for path in root.rglob("*.py"):
        if _is_allowlisted(path):
            continue
        yield path


class TestConnectFlowCompliance:
    def test_no_factory_bypass_in_production_trees(self):
        violations: list[str] = []
        for scan_dir in _SCAN_DIRS:
            for path in _iter_py_files(scan_dir):
                text = path.read_text(encoding="utf-8")
                for pattern in _FORBIDDEN_PATTERNS:
                    if pattern.search(text):
                        rel = path.relative_to(PROJECT_ROOT)
                        violations.append(f"{rel}: matches {pattern.pattern}")
        assert not violations, "Connect bypass violations:\n" + "\n".join(violations)

    def test_ui_commands_do_not_import_create_gateway(self):
        violations: list[str] = []
        for path in _iter_py_files(_UI_COMMANDS):
            text = path.read_text(encoding="utf-8")
            if (
                "create_gateway" in text
                and "connect_live" not in text
                and "connect_analytics" not in text
            ):
                # Allow docstrings/comments referencing legacy name in doctor docs only
                if path.name in {"__init__.py", "gateway_creation.py"}:
                    continue
                if "create_gateway" in text and (
                    "Uses ``create_gateway" in text
                    or ("create_gateway()" in text and "bootstrap_gateway" in text)
                ):
                    continue
            for line in text.splitlines():
                stripped = line.strip()
                if stripped.startswith("#"):
                    continue
                if "create_gateway(" in stripped and not stripped.startswith('"""'):
                    rel = path.relative_to(PROJECT_ROOT)
                    violations.append(f"{rel}: {stripped[:120]}")
        assert not violations, "UI commands must use connect.py shims:\n" + "\n".join(violations)

    def test_broker_registry_public_surface(self):
        from interface.ui.services import broker_registry

        assert "create_gateway" not in broker_registry.__all__
        assert "bootstrap_gateway" in broker_registry.__all__
        assert "require_gateway" in broker_registry.__all__

    def test_connect_shims_delegate_to_require_gateway(self):
        from unittest.mock import patch

        from interface.ui.services.connect import connect_live

        with patch(
            "interface.ui.services.connect.require_gateway",
            return_value="gw",
        ) as mock_req:
            assert connect_live("dhan") == "gw"
            mock_req.assert_called_once()
