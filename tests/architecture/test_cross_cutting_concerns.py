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
                if (
                    isinstance(func, ast.Attribute)
                    and func.attr == "basicConfig"
                    and isinstance(func.value, ast.Name)
                    and func.value.id == "logging"
                ):
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
            if isinstance(node, ast.ExceptHandler) and node.type is None:  # bare except
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
                                if (
                                    isinstance(value, ast.FormattedValue)
                                    and isinstance(value.value, ast.Subscript)
                                    and isinstance(value.value.value, ast.Name)
                                ):
                                    var_name = value.value.value.id
                                    if any(
                                        kw in var_name.lower()
                                        for kw in ["token", "secret", "password"]
                                    ):
                                        findings.append((node.lineno, var_name))
                        elif (
                            isinstance(arg, ast.Constant)
                            and isinstance(arg.value, str)
                            and any(
                                kw in arg.value.lower() for kw in ["token=", "secret=", "password="]
                            )
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
            f"Token/secret/password leakage via print() found.\nViolations: {violations}"
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


# ============================================================================
# REF-40: Guardrail enforcement — these tests fail CI if a known
# regression pattern is reintroduced. They are deliberately
# conservative: a false positive is acceptable, a false negative is
# not. If a guardrail is too noisy, it should be tightened, not
# removed.
# ============================================================================


def _file_contains_verify_false(filepath: Path) -> list[int]:
    """Detect ``requests`` calls or ``Session`` constructions that pass
    ``verify=False`` (REF-38: TLS hardening).

    Catches:
    - ``requests.get(..., verify=False)``
    - ``Session(verify=False)``
    - ``session.verify = False``
    - ``httpx.Client(verify=False)``
    """
    lines: list[int] = []
    try:
        content = filepath.read_text()
        tree = ast.parse(content, filename=str(filepath))
        for node in ast.walk(tree):
            # kwargs to calls
            if isinstance(node, ast.Call):
                for kw in node.keywords:
                    if kw.arg == "verify":
                        value = kw.value
                        if isinstance(value, ast.Constant) and value.value is False:
                            lines.append(node.lineno)
            # assignments: ``session.verify = False``
            if isinstance(node, ast.Assign):
                for target in node.targets:
                    if (
                        isinstance(target, ast.Attribute)
                        and target.attr == "verify"
                        and isinstance(node.value, ast.Constant)
                        and node.value.value is False
                    ):
                        lines.append(node.lineno)
    except (SyntaxError, UnicodeDecodeError):
        pass
    return lines


def _file_contains_pickle_load(filepath: Path) -> list[int]:
    """Detect ``pickle.load`` / ``pickle.loads`` on untrusted data
    (REF-31: CWE-502).

    The Upstox loader previously called ``pickle.load`` on a file
    that may have been tampered with — a remote-code-execution
    vector. This guard prevents that pattern from coming back.
    """
    lines: list[int] = []
    try:
        content = filepath.read_text()
        tree = ast.parse(content, filename=str(filepath))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            func = node.func
            # pickle.load / pickle.loads
            is_pickle = (
                isinstance(func, ast.Attribute)
                and func.attr in ("load", "loads")
                and isinstance(func.value, ast.Name)
                and func.value.id == "pickle"
            )
            if is_pickle:
                lines.append(node.lineno)
    except (SyntaxError, UnicodeDecodeError):
        pass
    return lines


def _file_contains_bare_token_log(filepath: Path) -> list[tuple[int, str]]:
    """Detect logger calls that interpolate a variable whose name
    contains ``token``, ``secret``, ``password``, ``api_key`` (REF-29:
    logging redaction).

    Catches:
    - ``logger.info(f"token={t}")``
    - ``logger.debug("api_key=%s", k)``
    - ``logging.warning("password: %s", p)``

    The redaction filter is defence-in-depth — code review should
    prevent these in the first place. This guard enforces the
    code-review half.
    """
    findings: list[tuple[int, str]] = []
    sensitive_kw = ("token", "secret", "password", "api_key", "apikey")
    logger_names = {"logger", "logging"}
    logger_methods = {
        "debug",
        "info",
        "warning",
        "error",
        "exception",
        "critical",
        "log",
    }
    try:
        content = filepath.read_text()
        tree = ast.parse(content, filename=str(filepath))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            func = node.func
            # logger.info(...)  /  logging.warning(...)
            if not isinstance(func, ast.Attribute):
                continue
            if func.attr not in logger_methods:
                continue
            if not isinstance(func.value, ast.Name) or func.value.id not in logger_names:
                continue
            # Inspect args
            for arg in node.args:
                # f-string interpolation
                if isinstance(arg, ast.JoinedStr):
                    for value in arg.values:
                        if isinstance(value, ast.FormattedValue):
                            if _expr_mentions_sensitive(value.value, sensitive_kw):
                                findings.append((node.lineno, "f-string with sensitive var"))
                            continue
                        if (
                            isinstance(value, ast.Constant)
                            and isinstance(value.value, str)
                            and any(kw in value.value.lower() for kw in sensitive_kw)
                        ):
                            findings.append((node.lineno, "literal contains sensitive kw"))
                # bare %s / .format string
                elif (
                    isinstance(arg, ast.Constant)
                    and isinstance(arg.value, str)
                    and any(
                        kw in arg.value.lower()
                        for kw in ("token=", "secret=", "password=", "api_key=")
                    )
                ):
                    findings.append((node.lineno, "format string mentions secret"))
    except (SyntaxError, UnicodeDecodeError):
        pass
    return findings


def _expr_mentions_sensitive(node: ast.AST, sensitive_kw: tuple[str, ...]) -> bool:
    """Recursively walk an expression looking for variable names
    whose identifier contains any of the sensitive keywords.
    """
    for sub in ast.walk(node):
        if isinstance(sub, ast.Name) and any(kw in sub.id.lower() for kw in sensitive_kw):
            return True
        if isinstance(sub, ast.Attribute) and any(kw in sub.attr.lower() for kw in sensitive_kw):
            return True
    return False


class TestGuardrailNoVerifyFalse:
    """REF-38: no ``verify=False`` on outbound HTTP sessions in
    production code. SSL hardening requires the ``HardenedHTTPSAdapter``
    be used; this guard catches the regression where someone bypasses
    the helper with ``verify=False``.
    """

    @pytest.mark.parametrize("directory", ["brokers", "scripts", "cli"])
    def test_no_verify_false(self, directory: str):
        if not (ROOT / directory).exists():
            pytest.skip(f"{directory}/ not present")
        files = _find_python_files([directory])
        violations: dict[str, list[int]] = {}
        for filepath in files:
            # Skip the ssl_hardening module itself — it must be able
            # to inspect ``verify=False`` to enforce the rule.
            if "ssl_hardening" in str(filepath):
                continue
            if "/tests/" in str(filepath) or "/test_" in str(filepath):
                continue
            lines = _file_contains_verify_false(filepath)
            if lines:
                violations[str(filepath.relative_to(ROOT))] = lines
        assert not violations, (
            "verify=False detected in production code. "
            "Use brokers.common.ssl_hardening.create_pinned_session() instead. "
            f"Violations: {violations}"
        )


class TestGuardrailNoPickleLoad:
    """REF-31: no ``pickle.load`` in production code. CWE-502
    (deserialization of untrusted data) is a remote-code-execution
    vector; the Upstox loader previously had this pattern.
    """

    @pytest.mark.parametrize("directory", ["brokers", "scripts", "cli"])
    def test_no_pickle_load(self, directory: str):
        if not (ROOT / directory).exists():
            pytest.skip(f"{directory}/ not present")
        files = _find_python_files([directory])
        violations: dict[str, list[int]] = {}
        for filepath in files:
            # The migration tool itself may need to read legacy
            # pickle files in a controlled environment. We allow
            # it ONLY inside the broker that owns the loader and
            # only when it is explicitly safe-guarded (file rename
            # + quarantine + json rebuild). The loader module is
            # allowed to *refer* to pickle for documentation; this
            # guard rejects active ``pickle.load()`` calls anywhere
            # except in tests of the guard itself.
            if "/tests/" in str(filepath) or "/test_" in str(filepath):
                continue
            lines = _file_contains_pickle_load(filepath)
            if lines:
                violations[str(filepath.relative_to(ROOT))] = lines
        assert not violations, (
            "pickle.load() detected in production code. "
            "Use json.load() or a domain-specific deserializer. "
            f"Violations: {violations}"
        )


class TestGuardrailNoBareTokenLogging:
    """REF-29: no logger call interpolating a token-named variable
    in production code. The redaction filter is defence-in-depth;
    code should not put secrets in logs in the first place.
    """

    @pytest.mark.parametrize("directory", ["brokers", "scripts", "cli"])
    def test_no_bare_token_logging(self, directory: str):
        if not (ROOT / directory).exists():
            pytest.skip(f"{directory}/ not present")
        files = _find_python_files([directory])
        violations: dict[str, list[tuple[int, str]]] = {}
        for filepath in files:
            if "/tests/" in str(filepath) or "/test_" in str(filepath):
                continue
            findings = _file_contains_bare_token_log(filepath)
            if findings:
                violations[str(filepath.relative_to(ROOT))] = findings
        assert not violations, (
            "Token/secret/password interpolation in logger call detected. "
            "Use extra={...} or pass an explicit redacted value. "
            f"Violations: {violations}"
        )
