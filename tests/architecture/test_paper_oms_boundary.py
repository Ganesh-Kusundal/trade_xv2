"""Architecture ratchet — paper-only OMS boundary (ADR-0012)."""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src"

_RESOLVER = SRC / "runtime" / "execution_target.py"
_ENUM_HOME = SRC / "domain" / "ports" / "execution_target.py"

# Modules allowed to mention ExecutionTargetKind without being the resolver.
_KIND_ALLOWLIST = frozenset(
    p.resolve()
    for p in (
        _RESOLVER,
        _ENUM_HOME,
        SRC / "application" / "execution" / "fill_source.py",
        SRC / "application" / "execution" / "oms_backtest_adapter.py",
        SRC / "application" / "execution" / "execution_engine.py",
        SRC / "application" / "execution" / "spine.py",
        SRC / "application" / "execution" / "place_order_use_case.py",
        SRC / "application" / "execution" / "__init__.py",
        SRC / "application" / "composer" / "execution.py",
        SRC / "application" / "ports.py",
        SRC / "domain" / "ports" / "__init__.py",
        SRC / "runtime" / "execution_config.py",
        SRC / "runtime" / "paper_session.py",
        SRC / "runtime" / "composition.py",
        SRC / "runtime" / "factory.py",
        SRC / "runtime" / "oms_composition.py",
        SRC / "application" / "oms" / "capital_provider.py",
        SRC / "interface" / "ui" / "services" / "oms_setup.py",
    )
)

_KIND_BRANCH = re.compile(
    r"ExecutionTargetKind\.(LIVE|PAPER|REPLAY|BACKTEST)|"
    r"ExecutionTargetKind\.from_str|"
    r'kind\s*=\s*["\']live["\']|'
    r'kind\s*=\s*["\']paper["\']',
)

_ORDER_ADAPTER_IMPORT = re.compile(
    r"^\s*(from\s+brokers\.(?:dhan|upstox)\.(?:orders|execution)[\w.]*\s+import|"
    r"import\s+brokers\.(?:dhan|upstox)\.(?:orders|execution))",
    re.MULTILINE,
)

_FORBIDDEN_ORDER_IMPORT_ROOTS = (
    SRC / "application",
    SRC / "analytics",
    SRC / "domain",
)


def test_execution_target_kind_branch_only_in_runtime_resolver() -> None:
    offenders: list[str] = []
    for path in SRC.rglob("*.py"):
        if path.resolve() in _KIND_ALLOWLIST:
            continue
        text = path.read_text(encoding="utf-8")
        if _KIND_BRANCH.search(text):
            offenders.append(path.relative_to(ROOT).as_posix())
    assert not offenders, (
        "ExecutionTargetKind branching belongs in runtime/execution_target.py only "
        f"(ADR-0012): {offenders}"
    )


def test_analytics_and_application_do_not_import_broker_order_adapters() -> None:
    offenders: list[str] = []
    for root in _FORBIDDEN_ORDER_IMPORT_ROOTS:
        for path in root.rglob("*.py"):
            text = path.read_text(encoding="utf-8")
            if _ORDER_ADAPTER_IMPORT.search(text):
                offenders.append(path.relative_to(ROOT).as_posix())
    assert not offenders, (
        "application/analytics/domain must not import broker order adapters — "
        f"use ExecutionTarget at runtime boundary: {offenders}"
    )


def test_paper_session_composer_exists() -> None:
    path = SRC / "runtime" / "paper_session.py"
    assert path.is_file(), "runtime/paper_session.py must exist (ADR-0012)"
    text = path.read_text(encoding="utf-8")
    assert "build_paper_session" in text
    assert "PaperFillSource" in text or "resolve_execution_target" in text
