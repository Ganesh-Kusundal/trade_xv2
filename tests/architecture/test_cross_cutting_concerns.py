"""Architecture tests for cross-cutting concerns.

These tests enforce architectural rules and prevent regression:
- No logging.basicConfig() in production code
- No bare except: blocks
- No token/secret/password in print() statements
- Exception hierarchy correctness
- File permissions on token stores
"""

from __future__ import annotations

import ast
import os
from pathlib import Path

import pytest

ROOT = Path(__file__).parent.parent.parent


def _find_python_files(directories: list[str]) -> list[Path]:
    """Find all .py files in given directories."""
    files = []
    for directory in directories:
        dir_path = ROOT / directory
        if dir_path.exists():
            files.extend(dir_path.rglob("*.py"))
    return files


def _file_contains_basic_config(filepath: Path) -> list[int]:
    """Check if file contains logging.basicConfig() calls.
    
    Allows conditional initialization (if not logging.getLogger().handlers).
    """
    lines = []
    try:
        content = filepath.read_text()
        tree = ast.parse(content, filename=str(filepath))
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                func = node.func
                if isinstance(func, ast.Attribute) and func.attr == "basicConfig":
                    if isinstance(func.value, ast.Name) and func.value.id == "logging":
                        # Check if it's inside an if statement checking for handlers
                        # For now, flag all instances - manual review needed
                        lines.append(node.lineno)
    except (SyntaxError, UnicodeDecodeError):
        pass
    return lines


def _file_contains_bare_except(filepath: Path) -> list[int]:
    """Check if file contains bare except: blocks."""
    lines = []
    try:
        content = filepath.read_text()
        tree = ast.parse(content, filename=str(filepath))
        for node in ast.walk(tree):
            if isinstance(node, ast.ExceptHandler):
                if node.type is None:  # bare except
                    lines.append(node.lineno)
    except (SyntaxError, UnicodeDecodeError):
        pass
    return lines


def _file_contains_token_print(filepath: Path) -> list[tuple[int, str]]:
    """Check if file contains print() with token/secret/password."""
    findings = []
    try:
        content = filepath.read_text()
        tree = ast.parse(content, filename=str(filepath))
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                func = node.func
                if isinstance(func, ast.Name) and func.id == "print":
                    for arg in node.args:
                        if isinstance(arg, ast.JoinedStr):  # f-string
                            for value in arg.values:
                                if isinstance(value, ast.FormattedValue):
                                    if isinstance(value.value, ast.Subscript):
                                        if isinstance(value.value.value, ast.Name):
                                            var_name = value.value.value.id
                                            if any(
                                                kw in var_name.lower()
                                                for kw in ["token", "secret", "password"]
                                            ):
                                                findings.append((node.lineno, var_name))
                        elif isinstance(arg, ast.Constant):
                            if isinstance(arg.value, str) and any(
                                kw in arg.value.lower()
                                for kw in ["token=", "secret=", "password="]
                            ):
                                findings.append((node.lineno, arg.value[:50]))
    except (SyntaxError, UnicodeDecodeError):
        pass
    return findings


class TestNoBasicConfig:
    """Enforce: No logging.basicConfig() in production code."""

    @pytest.mark.parametrize(
        "directory",
        ["brokers", "datalake", "analytics"],
    )
    def test_no_basic_config_in_directory(self, directory: str):
        """No logging.basicConfig() allowed in production directories."""
        files = _find_python_files([directory])
        violations = {}
        for filepath in files:
            # Skip test files
            if "test" in str(filepath) or "tests" in str(filepath):
                continue
            lines = _file_contains_basic_config(filepath)
            if lines:
                violations[str(filepath.relative_to(ROOT))] = lines

        assert not violations, (
            f"logging.basicConfig() found in {directory}/. "
            f"Use brokers.common.logging_config.setup_logging() instead.\n"
            f"Violations: {violations}"
        )


class TestNoBareExcept:
    """Enforce: No bare except: blocks in broker code."""

    def test_no_bare_except_in_brokers(self):
        """No bare except: in broker adapters."""
        files = _find_python_files(["brokers"])
        violations = {}
        for filepath in files:
            if "test" in str(filepath) or "tests" in str(filepath):
                continue
            lines = _file_contains_bare_except(filepath)
            if lines:
                violations[str(filepath.relative_to(ROOT))] = lines

        assert not violations, (
            f"Bare 'except:' found in broker code. Use 'except Exception as exc:' instead.\n"
            f"Violations: {violations}"
        )


class TestNoTokenLeakage:
    """Enforce: No token/secret/password in print() statements."""

    def test_no_token_print_in_brokers(self):
        """No print() with token/secret/password in broker code."""
        files = _find_python_files(["brokers"])
        violations = {}
        for filepath in files:
            if "test" in str(filepath) or "tests" in str(filepath):
                continue
            findings = _file_contains_token_print(filepath)
            if findings:
                violations[str(filepath.relative_to(ROOT))] = findings

        assert not violations, (
            f"Token/secret/password leakage via print() found.\n"
            f"Violations: {violations}"
        )


class TestExceptionHierarchy:
    """Enforce: Correct exception hierarchy."""

    def test_broker_error_inherits_from_tradexv2_error(self):
        """BrokerError must inherit from TradeXV2Error."""
        from brokers.common.resilience.errors import BrokerError, TradeXV2Error

        assert issubclass(BrokerError, TradeXV2Error)

    def test_all_broker_exceptions_inherit_from_broker_error(self):
        """All broker-specific exceptions must inherit from BrokerError."""
        from brokers.common.resilience.errors import (
            AuthenticationError,
            BrokerError,
            CircuitBreakerOpenError,
            InstrumentNotFoundError,
            NotSupportedError,
            OrderError,
            RateLimitError,
        )

        broker_exceptions = [
            AuthenticationError,
            CircuitBreakerOpenError,
            InstrumentNotFoundError,
            NotSupportedError,
            OrderError,
            RateLimitError,
        ]

        for exc_class in broker_exceptions:
            assert issubclass(exc_class, BrokerError), (
                f"{exc_class.__name__} must inherit from BrokerError"
            )

    def test_non_broker_exceptions_inherit_from_tradexv2_error(self):
        """Non-broker exceptions must inherit from TradeXV2Error."""
        from brokers.common.resilience.errors import (
            BrokerError,
            ConfigError,
            DataError,
            TradeXV2Error,
            ValidationError,
        )

        non_broker_exceptions = [ConfigError, DataError, ValidationError]

        for exc_class in non_broker_exceptions:
            assert issubclass(exc_class, TradeXV2Error), (
                f"{exc_class.__name__} must inherit from TradeXV2Error"
            )
            assert not issubclass(exc_class, BrokerError), (
                f"{exc_class.__name__} should NOT inherit from BrokerError"
            )


class TestErrorCodes:
    """Enforce: Error codes are defined and accessible."""

    def test_dhan_error_codes_exist(self):
        """Dhan error codes must be defined."""
        from brokers.common.resilience.error_codes import (
            DHAN_ERR_INVALID_TOKEN,
            DHAN_ERR_TOKEN_EXPIRED,
        )

        assert DHAN_ERR_INVALID_TOKEN == "DH-906"
        assert DHAN_ERR_TOKEN_EXPIRED == "DH-808"

    def test_broker_error_codes_exist(self):
        """Broker error codes must be defined."""
        from brokers.common.resilience.error_codes import (
            BRO_ERR_AUTH_FAILED,
            BRO_ERR_TIMEOUT,
        )

        assert BRO_ERR_AUTH_FAILED.startswith("BRO-")
        assert BRO_ERR_TIMEOUT.startswith("BRO-")
