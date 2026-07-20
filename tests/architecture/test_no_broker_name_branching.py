"""Architecture test: OMS + cert suite + rate limiter must never branch on
broker **name** strings.

This locks in DR-B1 / DR-B2 / DR-B3: adding a broker must require zero edits to
``application/oms``, the certification suite, or the resilience rate limiter.
Dispatch is capability-driven (``BrokerExtensionRegistry`` / ``BrokerPlugin``
capability metadata), not ``if broker_id == "dhan"``.

Concrete live-broker names that must never appear as a branching literal:
"""

from __future__ import annotations

from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SRC = REPO_ROOT / "src"

# Concrete *live* broker names.  Synthetic modes ("paper", "datalake") are an
# allowlist of non-live brokers and are intentionally excluded — they are not
# concrete broker identities that the OMS/cert/rate-limiter should branch on.
LIVE_BROKER_NAMES = {
    "dhan",
    "upstox",
    "zerodha",
    "angel",
    "kite",
    "fyers",
    "aliceblue",
    "icici",
    "kotak",
    "paytm",
    "5paisa",
    "edelweiss",
    "iifl",
    "mastertrust",
    "motilal",
    "sasonline",
    "tradejini",
    "samco",
    "trustline",
    "wisdom",
    "compositedge",
    "finvasia",
    "zebu",
}

OMS_DIR = SRC / "application" / "oms"
CERT_SUITE = SRC / "brokers" / "certification" / "suite.py"
RATE_LIMITER = SRC / "infrastructure" / "resilience" / "rate_limiter.py"


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _iter_oms_py() -> list[Path]:
    return sorted(OMS_DIR.rglob("*.py"))


def test_oms_has_no_live_broker_name_literals():
    """No concrete live-broker name may appear as a string literal in OMS."""
    violations: list[str] = []
    for path in _iter_oms_py():
        text = _read(path)
        for name in LIVE_BROKER_NAMES:
            # Match a quoted literal: "dhan" / 'dhan' / ="dhan"
            if f'"{name}"' in text or f"'{name}'" in text:
                violations.append(f"{path.relative_to(REPO_ROOT)}: literal {name!r}")
    assert not violations, "OMS branches on concrete broker names (DR-B1 violated):\n" + "\n".join(
        violations
    )


def test_oms_has_no_broker_name_comparisons():
    """No `broker_id ==` / `broker ==` / `in {..., "dhan", ...}` name branching."""
    import re

    pattern = re.compile(
        r'(broker_id|broker|\bbid\b)\s*(==|!=)\s*["\']([a-z0-9_]+)["\']'
        r'|["\']([a-z0-9_]+)["\']\s+(in|not\s+in)\s*[\(\{]'
    )
    violations: list[str] = []
    for path in _iter_oms_py():
        for lineno, line in enumerate(_read(path).splitlines(), 1):
            m = pattern.search(line)
            if not m:
                continue
            token = m.group(3) or m.group(5)
            if token in LIVE_BROKER_NAMES:
                violations.append(f"{path.relative_to(REPO_ROOT)}:{lineno}: {line.strip()}")
    assert not violations, (
        "OMS compares against concrete broker names (DR-B1 violated):\n" + "\n".join(violations)
    )


def test_cert_suite_no_broker_name_branch():
    """Cert suite must gate live-session checks via capability flag, not name."""
    import re

    text = _read(CERT_SUITE)
    # Forbid direct name comparisons in the suite body (docstrings excepted by
    # checking only code-ish lines is overkill; the only legitimate mention is
    # the explanatory docstring, so we target comparisons specifically).
    pattern = re.compile(r'broker_id\s*==\s*["\'](paper|dhan|upstox)["\']')
    hits = [f"{i}: {ln.strip()}" for i, ln in enumerate(text.splitlines(), 1) if pattern.search(ln)]
    assert not hits, "Cert suite still branches on broker name (DR-B2 violated):\n" + "\n".join(
        hits
    )


def test_rate_limiter_no_broker_name_branch():
    """Rate limiter must dispatch via capability metadata, not name imports."""
    import re

    text = _read(RATE_LIMITER)
    pattern = re.compile(
        r'broker_id\s*==\s*["\'](dhan|upstox)["\']'
        r'|import_module\(\s*["\']brokers\.(dhan|upstox)'
    )
    hits = [f"{i}: {ln.strip()}" for i, ln in enumerate(text.splitlines(), 1) if pattern.search(ln)]
    assert not hits, "Rate limiter still branches on broker name (DR-B3 violated):\n" + "\n".join(
        hits
    )


@pytest.mark.parametrize("name", sorted(LIVE_BROKER_NAMES))
def test_oms_dir_free_of_live_broker_name(name: str):
    """Parametric guard: each concrete broker name is absent from OMS source."""
    for path in _iter_oms_py():
        assert f'"{name}"' not in _read(path)
        assert f"'{name}'" not in _read(path)
