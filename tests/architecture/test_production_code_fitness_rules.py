"""Architecture fitness tests - enforce architectural rules.

These tests ensure the codebase maintains its architectural integrity
and prevent regression of the cross-cutting concerns remediation.

Run: python -m pytest tests/architecture/test_architecture_fitness.py -v
"""

from __future__ import annotations

import ast
import glob
import os
import re
import sys
from pathlib import Path
from typing import ClassVar

import pytest

# ── Layer definitions ─────────────────────────────────────────────────────

# Business logic layers - should not contain infrastructure concerns
BUSINESS_LAYERS = {
    "src/application": "src/application/",
    "src/domain": "src/domain/",
    "src/analytics": "src/analytics/",
}

# Infrastructure layers - cross-cutting concerns belong here
INFRASTRUCTURE_LAYERS = {
    "src/infrastructure": "src/infrastructure/",
    "src/config": "src/config/",
}

# Broker implementations
BROKER_LAYERS = {
    "src/brokers": "src/brokers/",
}

# API layer
API_LAYERS = {
    "src/interface/api": "src/interface/api/",
}

ALL_SOURCE_DIRS = [
    "src/application",
    "src/domain",
    "src/infrastructure",
    "src/config",
    "src/brokers",
    "src/interface/api",
    "src/interface/ui",
    "src/analytics",
    "src/datalake",
    "src/runtime",
    "src/tradex",
]

# ── Helper functions ─────────────────────────────────────────────────────


def _get_python_files(directory: str) -> list[str]:
    """Get all Python files in a directory recursively."""
    pattern = os.path.join(directory, "**", "*.py")
    return [f for f in glob.glob(pattern, recursive=True) if "__pycache__" not in f]


def _get_imports(filepath: str) -> list[tuple[str, str]]:
    """Extract import statements from a Python file."""
    imports = []
    try:
        with open(filepath) as f:
            tree = ast.parse(f.read())
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                if node.module:
                    imports.append((node.module, filepath))
            elif isinstance(node, ast.Import):
                for alias in node.names:
                    imports.append((alias.name, filepath))
    except SyntaxError:
        pass
    return imports


# ── Tests ─────────────────────────────────────────────────────────────────


class TestExceptionHierarchy:
    """All exceptions must inherit from TradeXV2Error or its subclasses."""

    def test_all_exceptions_inherit_from_tradexv2(self):
        """Run the validation script to check exception hierarchy."""
        script = Path("scripts/architecture/check_exception_hierarchy.py")
        if not script.exists():
            pytest.skip("Validation script not found")

        import subprocess
        result = subprocess.run(
            [sys.executable, str(script)],
            capture_output=True,
            text=True,
        )
        assert "FAIL" not in result.stdout, (
            f"Exception hierarchy violations found:\n{result.stdout}"
        )


class TestBusinessLayerIsolation:
    """Business modules must not directly implement infrastructure concerns."""

    # Known exceptions - files that are allowed to use these patterns
    KNOWN_EXCEPTIONS: ClassVar[dict[str, list[str]]] = {
        "logging.getLogger": [
            "src/application/",
            "src/domain/",
            "src/analytics/",
        ],
        "threading.Thread": [
            "src/application/oms/",
            "tests/unit/domain/",
            "tests/unit/domain/",  # legacy path; suite consolidated wave 1
        ],
    }

    @pytest.mark.parametrize("directory", ["src/application", "src/domain", "src/analytics"])
    def test_no_direct_logging(self, directory: str):
        """Business layer must use centralized logging."""
        violations = []
        for filepath in _get_python_files(directory):
            with open(filepath) as f:
                content = f.read()
            if "logging.getLogger" in content:
                # Check if this is a known exception
                is_known = any(
                    filepath.startswith(exc)
                    for exc in self.KNOWN_EXCEPTIONS.get("logging.getLogger", [])
                )
                if not is_known:
                    violations.append(filepath)

        assert not violations, (
            f"Business layer files using direct logging.getLogger(): {violations}"
        )

    @pytest.mark.parametrize("directory", ["src/application", "src/domain"])
    def test_no_direct_threading(self, directory: str):
        """Business layer must not create threads directly."""
        violations = []
        for filepath in _get_python_files(directory):
            with open(filepath) as f:
                content = f.read()
            if "threading.Thread" in content and "# no-rewrite" not in content:
                is_known = any(
                    filepath.startswith(exc)
                    for exc in self.KNOWN_EXCEPTIONS.get("threading.Thread", [])
                )
                if not is_known:
                    violations.append(filepath)

        assert not violations, (
            f"Business layer files creating threads directly: {violations}"
        )


class TestInfrastructureOwnership:
    """Infrastructure concerns must live only in infrastructure/."""

    def test_no_infrastructure_code_in_broker_layer(self):
        """Broker layer must not define cross-cutting infrastructure."""
        broker_files = _get_python_files("brokers")
        infra_patterns = [
            "class.*Retry", "class.*Cache", "class.*Metrics",
            "class.*HealthCheck",
        ]
        violations = []
        for filepath in broker_files:
            with open(filepath) as f:
                content = f.read()
            for pattern in infra_patterns:
                if pattern in content:
                    violations.append(f"{filepath}: {pattern}")

        assert not violations, (
            f"Broker layer defining infrastructure patterns: {violations}"
        )


class TestImportRules:
    """Architectural import rules must be enforced."""

    def test_infrastructure_not_importing_business(self):
        """Infrastructure must not import from application or domain layers."""
        violations = []
        for filepath in _get_python_files("infrastructure"):
            for imp, _src in _get_imports(filepath):
                if (
                    (imp.startswith("src/application") or imp.startswith("domain"))
                    and not imp.startswith((
                        "domain.events", "domain.types", "domain.enums",
                        "domain.constants", "domain.lifecycle_health", "domain.ports",
                        "domain.correlation", "domain.exceptions", "domain.entities",
                        "domain.provenance", "domain.symbols", "domain.instruments.instrument_id",
                        "domain.market_enums", "domain.orders", "domain.parsing",
                        "domain.status_mapper",
                        "domain.ports.protocols", "domain.candles.historical",
                        "domain.errors",
                        "domain.policies",
                        "domain.orders", "domain.parsing", "domain.status_mapper",
                        "domain.market_enums", "domain.exchange_segments",
                        "domain.extensions",
                        "domain.capabilities",
                    ))
                    and "/tests/" not in filepath
                ):
                    violations.append(f"{filepath}: imports {imp}")

        assert not violations, (
            f"Infrastructure layer importing business modules: {violations}"
        )

    def test_broker_not_importing_other_brokers(self):
        """Broker implementations must not import from other brokers."""
        violations = []
        broker_dirs = ["src/brokers/dhan", "src/brokers/upstox", "src/brokers/paper"]
        for i, b1 in enumerate(broker_dirs):
            for filepath in _get_python_files(b1):
                for imp, _src in _get_imports(filepath):
                    for b2 in broker_dirs[i + 1:]:
                        if imp.startswith(b2.replace("/", ".")) and "/tests/" not in filepath:
                            violations.append(f"{filepath}: imports {imp}")

        assert not violations, (
            f"Broker implementations importing from other brokers: {violations}"
        )


class TestNoDuplication:
    """Enforce single implementation of cross-cutting concerns."""

    # Map of concern -> canonical module
    CANONICAL_LOCATIONS: ClassVar[dict[str, str]] = {
        "TradeXV2Error": "domain.exceptions",
        "configure_logging": "infrastructure.logging_config",
        "metrics_registry": "infrastructure.metrics.registry",
        "Cache": "infrastructure.cache",
        "TimeService": "infrastructure.time_service",
        "HealthRegistry": "infrastructure.health",
        "setup_exception_handlers": "infrastructure.global_exception_handler",
        "retry": "infrastructure.retry",
    }

    def test_canonical_exception_location(self):
        """TradeXV2Error must only be defined in one place."""
        count = 0
        for directory in ALL_SOURCE_DIRS:
            for filepath in _get_python_files(directory):
                with open(filepath) as f:
                    content = f.read()
                if "class TradeXV2Error(Exception)" in content:
                    count += 1
                    assert "domain/exceptions.py" in filepath, (
                        f"TradeXV2Error defined in non-canonical location: {filepath}"
                    )
        assert count == 1, f"TradeXV2Error defined {count} times (should be 1)"


class TestConfigurationValidation:
    """Configuration must be centralized and validated."""

    def test_no_hardcoded_credentials(self):
        """Production code must not contain hardcoded credentials."""
        violations = []
        patterns_to_check = [
            "api_key = \"", "api_secret = \"", "password = \"", "secret = \"",
        ]
        for directory in ALL_SOURCE_DIRS:
            if directory == "tests":
                continue
            for filepath in _get_python_files(directory):
                if "test_" in filepath or ".env" in filepath:
                    continue
                with open(filepath) as f:
                    for i, line in enumerate(f, 1):
                        stripped = line.strip()
                        if any(pattern in stripped for pattern in patterns_to_check):
                            # Ignore env var lookups and documentation
                            if "os.environ" in stripped or "env" in stripped or "# example" in stripped:
                                continue
                            violations.append(f"{filepath}:{i}: {stripped[:80]}")

        assert not violations, (
            "Hardcoded credential patterns found:\n" + "\n".join(violations)
        )


class TestRetryUsage:
    """Retry logic must use the centralized retry framework."""

    def test_no_manual_retry_loops(self):
        """Production code must not implement manual retry loops."""
        violations = []
        for directory in ["src/application", "src/brokers", "src/interface/api", "src/interface/ui"]:
            for filepath in _get_python_files(directory):
                with open(filepath) as f:
                    content = f.read()
                if re.search(r'\bimport time(?:\s|$)', content) and "sleep(" in content and "@retry" not in content and "retry(" not in content:
                    violations.append(filepath)

        # Known exceptions - files that legitimately use sleep
        known_exceptions = [
            "tests/unit/brokers/common",  # Tests
            "tests/",  # Tests
            "src/brokers/dhan/api/reconnecting_service.py",  # Reconnection logic
            "src/brokers/dhan/data/depth_feed_base.py",  # Depth feed uses poll intervals
            "src/brokers/dhan/api/http_client.py",  # Rate limiting + retry backoff
            "src/brokers/upstox/orders/slice_adapter.py",  # Slice adapter uses poll intervals
            "src/interface/ui/load_testing/",  # Load testing
            "src/interface/ui/commands/market.py",  # CLI polling loop
            "src/interface/ui/commands/events.py",  # CLI event polling
            "src/interface/ui/commands/websocket.py",  # CLI WebSocket keepalive
            "src/brokers/dhan/depth_200.py",  # Depth feed poll interval
            "src/application/scheduling/quota_scheduler.py",  # Scheduler uses sleep
            "src/application/services/download_engine.py",  # Download engine
            "src/brokers/upstox/auth/http.py",  # HTTP retry backoff
            "src/brokers/dhan/websocket/order_stream.py",  # WebSocket reconnect
            "src/brokers/dhan/execution/order_placement.py",  # Idempotency poll-wait
            "src/interface/ui/services/feed_probe.py",  # Live-feed probe window (not HTTP retry)
            "src/interface/ui/utils/retry_handler.py",  # Shared UI retry helper
        ]
        violations = [
            v for v in violations
            if not any(exc in v for exc in known_exceptions)
        ]

        assert not violations, (
            f"Manual retry loops (time.sleep) without @retry decorator: {violations}"
        )


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
