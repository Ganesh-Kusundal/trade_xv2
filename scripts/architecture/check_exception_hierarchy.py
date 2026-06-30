#!/usr/bin/env python3
"""Verify all exceptions inherit from TradeXV2Error.

This script enforces the architectural rule that ALL custom exceptions
must inherit from TradeXV2Error to ensure consistent error handling.

Usage:
    python scripts/architecture/check_exception_hierarchy.py
"""

from __future__ import annotations

import ast
import sys
from pathlib import Path
from typing import NamedTuple


class ExceptionViolation(NamedTuple):
    """Represents an exception hierarchy violation."""
    file: str
    line: int
    class_name: str
    base_class: str
    message: str


# Directories to scan
SCAN_DIRS = [
    Path("brokers"),
    Path("application"),
    Path("infrastructure"),
    Path("domain"),
    Path("config"),
    Path("cli"),
    Path("api"),
    Path("datalake"),
    Path("analytics"),
    Path("market_data"),
    Path("runtime"),
]

# Files to exclude (test files, __pycache__, etc.)
EXCLUDE_PATTERNS = [
    "*/tests/*",
    "*/__pycache__/*",
    "*.pyc",
    "*/test_*.py",
]

# The canonical base exception and its known subclasses
CANONICAL_BASE = "TradeXV2Error"
KNOWN_GOOD_BASES = {
    "TradeXV2Error",
    "BrokerError",  # Inherits from TradeXV2Error
    "RetryableError",  # Inherits from BrokerError
    "NonRetryableError",  # Inherits from BrokerError
    "RateLimitError",  # Inherits from BrokerError
    "CircuitBreakerOpenError",  # Inherits from BrokerError
    "AuthenticationError",  # Inherits from BrokerError
    "InstrumentNotFoundError",  # Inherits from BrokerError
    "OrderError",  # Inherits from BrokerError
    "NotSupportedError",  # Inherits from BrokerError
    "ExitAllError",  # Inherits from NotSupportedError
    "BrokerDegradedError",  # Inherits from BrokerError
    "DataError",  # Inherits from TradeXV2Error
    "ConfigError",  # Inherits from TradeXV2Error
    "ValidationError",  # Inherits from TradeXV2Error
    "DhanError",  # Inherits from BrokerError
    "UpstoxApiError",  # Inherits from BrokerError
    "UpstoxAuthError",  # Inherits from UpstoxApiError
    "StreamError",  # Inherits from BrokerError
    "NetworkError",  # Inherits from RetryableError
}

# Standard library exceptions that are OK to inherit from
ALLOWED_STANDARD_BASES = {
    "ValueError",
    "TypeError",
    "KeyError",
    "AttributeError",
    "ImportError",
    "ModuleNotFoundError",
}


def should_exclude(file_path: Path) -> bool:
    """Check if file should be excluded from scanning."""
    for pattern in EXCLUDE_PATTERNS:
        if file_path.match(pattern):
            return True
    return False


def _inherits_from_good_base(
    class_name: str,
    hierarchy: dict[str, list[str]],
    visited: set[str] | None = None,
) -> bool:
    """Recursively check if class_name inherits from a known-good base."""
    if visited is None:
        visited = set()
    if class_name in KNOWN_GOOD_BASES:
        return True
    if class_name in visited or class_name not in hierarchy:
        return False
    visited.add(class_name)
    return any(
        _inherits_from_good_base(parent, hierarchy, visited)
        for parent in hierarchy[class_name]
    )


def scan_file(file_path: Path) -> list[ExceptionViolation]:
    """Scan a single file for exception hierarchy violations."""
    violations = []

    try:
        with open(file_path, encoding="utf-8") as f:
            content = f.read()

        tree = ast.parse(content)

        # Build a map of class -> base classes in this file
        class_hierarchy: dict[str, list[str]] = {}
        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef):
                bases = []
                for base in node.bases:
                    if isinstance(base, ast.Name):
                        bases.append(base.id)
                class_hierarchy[node.name] = bases

        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef):
                # Skip the canonical base class itself
                if node.name == CANONICAL_BASE:
                    continue

                # Check if this is an exception class
                base_classes = class_hierarchy.get(node.name, [])
                is_exception = any(
                    "Error" in base or "Exception" in base for base in base_classes
                )

                if not is_exception:
                    continue

                # Check if it inherits from a known good base (directly or transitively)
                inherits_from_good = any(
                    base in KNOWN_GOOD_BASES or _inherits_from_good_base(base, class_hierarchy)
                    for base in base_classes
                )

                # Check if it inherits from an allowed standard library exception
                inherits_from_standard = any(
                    base in ALLOWED_STANDARD_BASES for base in base_classes
                )

                # Skip if it inherits from a good base or allowed standard base
                if inherits_from_good or inherits_from_standard:
                    continue

                # This is a violation - inherits from unknown base
                primary_base = base_classes[0] if base_classes else "Exception"

                violations.append(
                    ExceptionViolation(
                        file=str(file_path),
                        line=node.lineno,
                        class_name=node.name,
                        base_class=primary_base,
                        message=f"{node.name} inherits from {primary_base}, not {CANONICAL_BASE} or its subclasses",
                    )
                )

    except SyntaxError as e:
        print(f"⚠️  Syntax error in {file_path}: {e}", file=sys.stderr)
    except Exception as e:
        print(f"⚠️  Error scanning {file_path}: {e}", file=sys.stderr)

    return violations


def scan_codebase() -> list[ExceptionViolation]:
    """Scan entire codebase for exception hierarchy violations."""
    all_violations = []

    for scan_dir in SCAN_DIRS:
        if not scan_dir.exists():
            continue

        for file_path in scan_dir.rglob("*.py"):
            if should_exclude(file_path):
                continue

            violations = scan_file(file_path)
            all_violations.extend(violations)

    return all_violations


def print_report(violations: list[ExceptionViolation]) -> None:
    """Print a formatted report of violations."""
    if not violations:
        print("✅ No exception hierarchy violations found!")
        return

    print(f"\n❌ Found {len(violations)} exception hierarchy violations:\n")

    # Group by file
    by_file: dict[str, list[ExceptionViolation]] = {}
    for v in violations:
        by_file.setdefault(v.file, []).append(v)

    for file_path in sorted(by_file.keys()):
        print(f"\n📄 {file_path}")
        for v in by_file[file_path]:
            print(f"   Line {v.line}: {v.class_name}")
            print(f"   → {v.message}")
            print(f"   Fix: class {v.class_name}({CANONICAL_BASE}):")


def main() -> int:
    """Main entry point."""
    print("🔍 Scanning for exception hierarchy violations...\n")

    violations = scan_codebase()
    print_report(violations)

    if violations:
        print(f"\n❌ FAIL: Found {len(violations)} violations")
        print("\nTo fix these violations:")
        print("1. Import TradeXV2Error: from brokers.common.resilience.errors import TradeXV2Error")
        print(f"2. Change base class to {CANONICAL_BASE} or a known subclass")
        print("3. Ensure the exception hierarchy is consistent")
        return 1
    else:
        print("\n✅ PASS: All exceptions follow the canonical hierarchy")
        return 0


if __name__ == "__main__":
    sys.exit(main())
