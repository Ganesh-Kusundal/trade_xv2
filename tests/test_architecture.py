"""Architectural invariant tests.

These tests enforce structural rules that keep the codebase maintainable
and prevent regression as the team scales.

Run with: pytest tests/test_architecture.py -v
"""

import ast
from pathlib import Path

ROOT = Path(__file__).parent.parent


def _get_python_files(directory: str) -> list[Path]:
    """Get all Python files in a directory, excluding test files.
    
    Test files often import from multiple modules for integration testing
    and should not be subject to import direction rules.
    """
    all_files = list((ROOT / directory).rglob("*.py"))
    # Exclude test files and test directories
    return [
        f for f in all_files
        if "/tests/" not in str(f) and "/test_" not in str(f)
    ]


def _get_imports(file_path: Path) -> list[str]:
    """Extract import statements from a Python file."""
    try:
        tree = ast.parse(file_path.read_text())
    except SyntaxError:
        return []

    imports = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                imports.append(alias.name)
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                imports.append(node.module)
    return imports


class TestImportDirection:
    """Import direction rules - prevent circular dependencies."""

    def test_brokers_common_does_not_import_dhan(self):
        """brokers.common cannot import from brokers.dhan."""
        violations = []
        for py_file in _get_python_files("brokers/common"):
            imports = _get_imports(py_file)
            for imp in imports:
                if "brokers.dhan" in imp:
                    violations.append(f"{py_file.relative_to(ROOT)} imports {imp}")

        assert not violations, (
            f"brokers.common must not import from brokers.dhan:\n"
            + "\n".join(violations)
        )

    def test_brokers_common_does_not_import_upstox(self):
        """brokers.common cannot import from brokers.upstox."""
        violations = []
        for py_file in _get_python_files("brokers/common"):
            imports = _get_imports(py_file)
            for imp in imports:
                if "brokers.upstox" in imp:
                    violations.append(f"{py_file.relative_to(ROOT)} imports {imp}")

        assert not violations, (
            f"brokers.common must not import from brokers.upstox:\n"
            + "\n".join(violations)
        )

    def test_brokers_dhan_does_not_import_upstox(self):
        """brokers.dhan cannot import from brokers.upstox."""
        violations = []
        for py_file in _get_python_files("brokers/dhan"):
            imports = _get_imports(py_file)
            for imp in imports:
                if "brokers.upstox" in imp:
                    violations.append(f"{py_file.relative_to(ROOT)} imports {imp}")

        assert not violations, (
            f"brokers.dhan must not import from brokers.upstox:\n"
            + "\n".join(violations)
        )

    def test_brokers_upstox_does_not_import_dhan(self):
        """brokers.upstox cannot import from brokers.dhan."""
        violations = []
        for py_file in _get_python_files("brokers/upstox"):
            imports = _get_imports(py_file)
            for imp in imports:
                if "brokers.dhan" in imp:
                    violations.append(f"{py_file.relative_to(ROOT)} imports {imp}")

        assert not violations, (
            f"brokers.upstox must not import from brokers.dhan:\n"
            + "\n".join(violations)
        )

    def test_datalake_does_not_import_cli(self):
        """datalake cannot import from cli."""
        violations = []
        for py_file in _get_python_files("datalake"):
            imports = _get_imports(py_file)
            for imp in imports:
                if imp.startswith("cli"):
                    violations.append(f"{py_file.relative_to(ROOT)} imports {imp}")

        assert not violations, (
            f"datalake must not import from cli:\n" + "\n".join(violations)
        )

    def test_analytics_does_not_import_cli(self):
        """analytics cannot import from cli."""
        violations = []
        for py_file in _get_python_files("analytics"):
            imports = _get_imports(py_file)
            for imp in imports:
                if imp.startswith("cli"):
                    violations.append(f"{py_file.relative_to(ROOT)} imports {imp}")

        assert not violations, (
            f"analytics must not import from cli:\n" + "\n".join(violations)
        )

    def test_no_shim_imports_in_production_code(self):
        """Production code must not import from deprecated shim paths.

        All imports from brokers.common.core.{domain,types,field_mapping,requests,
        result,reconciliation,exchange_segments,parsing} must migrate to the
        canonical domain/ imports. Only the shim files themselves are exempt.

        REF: Architecture Audit Phase 11 — Hidden Dependencies & Coupling Audit
        """
        SHIM_PATTERNS = [
            "brokers.common.core.domain",
            "brokers.common.core.types",
            "brokers.common.core.field_mapping",
            "brokers.common.core.requests",
            "brokers.common.core.result",
            "brokers.common.core.reconciliation",
            "brokers.common.core.exchange_segments",
            "brokers.common.core.parsing",
        ]

        # Files that ARE the shims — they MUST import from themselves
        SHIM_FILE_PATHS = {
            str(ROOT / "brokers/common/core/models.py"),
            str(ROOT / "brokers/common/core/types.py"),
            str(ROOT / "brokers/common/core/field_mapping.py"),
            str(ROOT / "brokers/common/core/requests.py"),
            str(ROOT / "brokers/common/core/result.py"),
            str(ROOT / "brokers/common/core/reconciliation.py"),
            str(ROOT / "brokers/common/core/exchange_segments.py"),
            str(ROOT / "brokers/common/core/parsing.py"),
            str(ROOT / "brokers/common/core/__init__.py"),
        }

        violations = []
        for directory in ["brokers", "datalake", "analytics", "cli", "domain", "tests"]:
            dir_path = ROOT / directory
            if not dir_path.exists():
                continue
            for py_file in dir_path.rglob("*.py"):
                # Skip __pycache__ and the shim files themselves
                if "__pycache__" in str(py_file):
                    continue
                if str(py_file) in SHIM_FILE_PATHS:
                    continue
                imports = _get_imports(py_file)
                for imp in imports:
                    for pattern in SHIM_PATTERNS:
                        if imp == pattern or imp.startswith(pattern + "."):
                            violations.append(
                                f"{py_file.relative_to(ROOT)} imports {imp}"
                            )
                            break

        assert not violations, (
            f"{len(violations)} shim imports found in non-shim files. "
            f"Migrate to canonical domain/ imports.\n"
            f"Run: python scripts/migrate_shim_imports.py --apply\n"
            + "\n".join(violations[:20])
            + ("\n..." if len(violations) > 20 else "")
        )

    def test_no_direct_event_bus_internal_imports(self):
        """No file should import from the deprecated brokers/common/event_bus/ path.

        After the EventBus elevation (Wave 2-3) and shim cleanup (Wave 5),
        all event_bus code lives at infrastructure/event_bus/. The old
        brokers/common/event_bus/ path is no longer a valid import target.

        REF: Architecture Audit Phase 7 (Wave 3) + Wave 5 shim cleanup.
        """
        INTERNAL_PATTERNS = [
            "brokers.common.event_bus.event_bus",
            "brokers.common.event_bus.dead_letter_queue",
            "brokers.common.event_bus.factory",
            "brokers.common.event_bus.models",
            "brokers.common.event_bus.event_types",
            "brokers.common.event_bus.processed_trade_repository",
        ]

        violations = []
        for directory in ["brokers", "datalake", "analytics", "cli", "domain", "tests", "infrastructure", "scripts"]:
            dir_path = ROOT / directory
            if not dir_path.exists():
                continue
            for py_file in dir_path.rglob("*.py"):
                if "__pycache__" in str(py_file):
                    continue
                imports = _get_imports(py_file)
                for imp in imports:
                    for pattern in INTERNAL_PATTERNS:
                        if imp == pattern or imp.startswith(pattern + "."):
                            violations.append(
                                f"{py_file.relative_to(ROOT)} imports {imp}"
                            )
                            break

        assert not violations, (
            f"{len(violations)} direct event_bus internal imports found. "
            f"Import from infrastructure.event_bus instead.\n"
            + "\n".join(violations[:15])
            + ("\n..." if len(violations) > 15 else "")
        )


class TestModuleBoundaries:
    """Module boundary tests - enforce clean architecture."""

    def test_brokers_init_only_exports_common_types(self):
        """brokers/__init__.py should only export broker-agnostic types."""
        init_file = ROOT / "brokers" / "__init__.py"
        content = init_file.read_text()

        # Should not export Dhan-specific types
        dhan_specific = [
            "DhanConnection",
            "DhanHttpClient",
            "DhanMarketFeed",
            "DhanOrderStream",
            "SymbolResolver",
            "InstrumentLoader",
            "BrokerFactory",
            "BrokerGateway",
        ]

        violations = [
            name for name in dhan_specific
            if f'"{name}"' in content or f"'{name}'" in content
        ]

        assert not violations, (
            f"brokers/__init__.py should not export Dhan-specific types: {violations}\n"
            f"Import directly from brokers.dhan instead."
        )

    def test_dhan_has_all_declaration(self):
        """brokers/dhan/__init__.py must have __all__."""
        init_file = ROOT / "brokers" / "dhan" / "__init__.py"
        content = init_file.read_text()

        assert "__all__" in content, "brokers/dhan/__init__.py must define __all__"

    def test_upstox_has_all_declaration(self):
        """brokers/upstox/__init__.py must have __all__."""
        init_file = ROOT / "brokers" / "upstox" / "__init__.py"
        content = init_file.read_text()

        assert "__all__" in content, "brokers/upstox/__init__.py must define __all__"

    def test_brokers_common_has_all_declaration(self):
        """brokers/common/__init__.py must have __all__."""
        init_file = ROOT / "brokers" / "common" / "__init__.py"
        content = init_file.read_text()

        assert "__all__" in content, "brokers/common/__init__.py must define __all__"


class TestNamingConventions:
    """Naming convention tests."""

    def test_exception_classes_end_with_error(self):
        """All exception classes should end with 'Error'."""
        violations = []
        for directory in ["brokers/common", "brokers/dhan", "brokers/upstox"]:
            for py_file in _get_python_files(directory):
                try:
                    tree = ast.parse(py_file.read_text())
                except SyntaxError:
                    continue

                for node in ast.walk(tree):
                    if isinstance(node, ast.ClassDef):
                        # Check if it's an exception (inherits from Exception or BaseException)
                        for base in node.bases:
                            if isinstance(base, ast.Name) and base.id in ("Exception", "BaseException", "BrokerError"):
                                if not node.name.endswith("Error"):
                                    violations.append(f"{py_file.relative_to(ROOT)}: {node.name}")

        # This is a soft check - we only warn, don't fail
        if violations:
            print(f"\nWarning: Exceptions not ending with 'Error': {violations}")


class TestDocumentation:
    """Documentation presence tests."""

    def test_all_public_modules_have_docstrings(self):
        """All __init__.py files should have module docstrings."""
        init_files = list(ROOT.rglob("__init__.py"))

        violations = []
        for init_file in init_files:
            # Skip test files
            if "tests/" in str(init_file):
                continue

            try:
                tree = ast.parse(init_file.read_text())
                docstring = ast.get_docstring(tree)
                if not docstring or len(docstring) < 20:
                    violations.append(str(init_file.relative_to(ROOT)))
            except SyntaxError:
                pass

        # Soft check - just warn
        if violations:
            print(f"\nWarning: Modules without docstrings: {violations}")
