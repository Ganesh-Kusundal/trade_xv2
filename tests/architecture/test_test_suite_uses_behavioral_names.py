"""Test files must name guarantees, not implementation history."""

from __future__ import annotations

from pathlib import Path

# Filenames that encode sprint/phase/ticket history instead of behavior.
_FORBIDDEN_SUBSTRINGS = (
    "phase0",
    "phase1",
    "phase2",
    "phase3",
    "phase4",
    "phase5",
    "phase6",
    "phase7",
    "phase_",
    "_b7_",
    "b7_",
    "remediation_",
    "after_refactor",
    "new_feature",
    "issue_",
    "sprint_",
    "wave_",
    "fix_bug",
    # History / ticket vocabulary (wave 4)
    "architecture_regression",
    "circuit_breaker_regression",
    "gateway_issues_regression",
    "regression_fixes",
    "regression_suite",
    "websocket_regression",
    "event_bus_legacy",
    "architecture_fitness",
    # Process / implementation vocabulary
    "recent_fixes",
    "wireup",
    "migration",
)

_ROOT = Path(__file__).resolve().parents[2]


def _test_files() -> list[Path]:
    files: list[Path] = []
    for base in (_ROOT / "tests", _ROOT / "src"):
        if not base.is_dir():
            continue
        for path in base.rglob("test_*.py"):
            if "__pycache__" in path.parts:
                continue
            files.append(path)
    return files


def test_no_history_encoded_test_filenames() -> None:
    """Reject test_*.py names that describe tickets/phases rather than behavior."""
    offenders: list[str] = []
    for path in _test_files():
        name = path.name.lower()
        for token in _FORBIDDEN_SUBSTRINGS:
            if token in name:
                offenders.append(f"{path.relative_to(_ROOT)} (matched {token!r})")
                break
    assert not offenders, (
        "Rename history-named tests to behavioral contracts (see tests/README.md):\n"
        + "\n".join(offenders)
    )


def test_pyramid_directories_exist() -> None:
    """Top-level pyramid layout is present under tests/."""
    for name in ("unit", "component", "integration", "e2e", "architecture"):
        assert (_ROOT / "tests" / name).is_dir(), f"missing tests/{name}"


def test_domain_and_oms_tests_live_under_pyramid() -> None:
    """Wave-1 consolidation: no package-local domain/oms test suites under src/."""
    domain_tests = _ROOT / "src" / "domain" / "tests"
    oms_tests = _ROOT / "src" / "application" / "oms" / "tests"
    assert not domain_tests.is_dir(), "domain tests must live under tests/unit/domain"
    assert not oms_tests.is_dir(), "OMS tests must live under tests/component/oms"
    assert (_ROOT / "tests" / "unit" / "domain").is_dir()
    assert (_ROOT / "tests" / "component" / "oms").is_dir()


def test_broker_and_api_tests_live_under_pyramid() -> None:
    """Wave-2: broker/API suites live under tests/{unit,integration}, not src or legacy tops."""
    for legacy in ("api", "oms", "contract", "runtime", "regression", "capability"):
        assert not (_ROOT / "tests" / legacy).is_dir(), f"legacy tests/{legacy} must be folded"
    for broker in ("dhan", "upstox", "paper", "common"):
        pkg_tests = _ROOT / "src" / "brokers" / broker / "tests"
        assert not pkg_tests.is_dir(), f"broker tests must not live under {pkg_tests}"
    assert (_ROOT / "tests" / "unit" / "brokers" / "dhan").is_dir()
    assert (_ROOT / "tests" / "integration" / "api").is_dir()


def test_no_package_local_tests_under_src() -> None:
    """Wave-3: production packages must not host test_*.py trees."""
    offenders: list[str] = []
    src = _ROOT / "src"
    if src.is_dir():
        for path in src.rglob("test_*.py"):
            if "__pycache__" in path.parts:
                continue
            offenders.append(str(path.relative_to(_ROOT)))
    assert not offenders, "Move package-local tests into tests/ pyramid:\n" + "\n".join(offenders)
    for name in ("analytics", "datalake", "infrastructure", "config"):
        assert (_ROOT / "tests" / "unit" / name).is_dir(), f"missing tests/unit/{name}"
    assert (_ROOT / "tests" / "component" / "ui").is_dir()
