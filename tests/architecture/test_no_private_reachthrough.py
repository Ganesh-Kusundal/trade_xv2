"""Architecture test: prevent regression on SM-04 private reach-through fixes.

Targets the 3 highest-risk sites that were fixed to use public accessors:
1. reconciliation_service.py reaching into _order_manager._lifecycle / ._trade_recorder
2. order_placer.py reaching into risk_manager._capital_provider
3. context.py reaching into _order_manager._order_store

Also enforces a broader scan of domain/, application/, and infrastructure/
layers to prevent new private getattr reach-throughs from being introduced.
"""

import subprocess

import pytest


@pytest.mark.architecture
def test_sm04_no_private_reachthrough_regression():
    """SM-04: highest-risk getattr reach-throughs must not regress."""
    # Each tuple: (file, forbidden_literal_string, description)
    blocked = [
        (
            "src/application/oms/reconciliation_service.py",
            'getattr(self._order_manager, "_lifecycle"',
            "ReconciliationService must use order_manager.lifecycle, not getattr(_lifecycle)",
        ),
        (
            "src/application/oms/reconciliation_service.py",
            'getattr(self._order_manager, "_trade_recorder"',
            "ReconciliationService must use order_manager.trade_recorder, not getattr(_trade_recorder)",
        ),
        (
            "src/application/trading/order_placer.py",
            "rm._capital_provider",
            "OrderPlacer must use rm.capital_provider, not rm._capital_provider",
        ),
        (
            "src/application/oms/context.py",
            'getattr(self._order_manager, "_order_store"',
            "Context must use order_manager.order_store, not getattr(_order_store)",
        ),
    ]

    for filepath, forbidden, description in blocked:
        result = subprocess.run(
            ["grep", "-n", forbidden, filepath],
            capture_output=True,
            text=True,
        )
        matches = [
            line for line in result.stdout.strip().split("\n") if line and "# noqa" not in line
        ]
        assert not matches, (
            f"SM-04 regression: {description}\n"
            f"  File: {filepath}\n"
            f"  Matches:\n" + "\n".join(f"    {m}" for m in matches)
        )


# Allowed patterns: getattr on self for lazily-attached attrs, getattr on
# value objects / reports for safe fallback, getattr on broker internals
# (adapter layer), and getattr on third-party objects.
_ALLOWLIST_PATTERNS = [
    # Self-access for lazily-attached composition-root attrs (hasattr guard is OK)
    'getattr(self, "_',
    # Report / value-object fallback (defensive getattr on typed VOs)
    'getattr(report, "_',
    'getattr(d, "_',
    # Status / provider fallback (defensive getattr)
    'getattr(self._status, "_',
    'getattr(q, "_',
    # Broker / extension internal access (lower priority — broker-adapter layer)
    'getattr(gw, "_',
    'getattr(gateway, "_',
    'getattr(conn, "_',
    'getattr(auth, "_',
    'getattr(client, "_',
    'getattr(broker_obj, "_',
    'getattr(sub, "_',
    'getattr(sub_conn, "_',
    'getattr(ws, "_',
    'getattr(mf, "_',
    'getattr(sched, "_',
    'getattr(upstox_gw, "_',
    # Factory wiring utilities (internal composition)
    'getattr(md, "_',
    'getattr(self._svc, "_',
    'getattr(self._bus, "_',
    # Exception / exc fallback
    'getattr(exc, "_',
    'getattr(self._order_service, "',
    'getattr(provider, "',
    'getattr(b, "',
    'getattr(ext, "_symbol"',
    'getattr(ext, "_exchange"',
    'getattr(found, "',
    # Test / diagnostic getattr on public methods
    'getattr(self._svc, "upstox_',
]

# Scan paths: the architecturally important layers
_SCAN_PATHS = [
    "src/domain/",
    "src/application/",
    "src/infrastructure/",
]


def _is_allowed(line: str) -> bool:
    """Return True if this getattr line matches an allowed pattern."""
    stripped = line.strip()
    # Allow comments and noqa
    if stripped.startswith("#") or "# noqa" in stripped:
        return True
    return any(pattern in stripped for pattern in _ALLOWLIST_PATTERNS)


@pytest.mark.architecture
def test_no_private_reachthrough_in_important_layers():
    """Private getattr(obj, '_foo') must not exist in domain/application/infrastructure.

    Only explicitly allowlisted patterns (broker-internal wiring, self-access
    for lazily-attached attrs, report/VO fallback) are permitted.
    """
    result = subprocess.run(
        ["grep", "-rn", "--include=*.py", 'getattr(.*"_[a-z]', *_SCAN_PATHS],
        capture_output=True,
        text=True,
    )
    if not result.stdout.strip():
        return  # no hits at all — clean

    lines = result.stdout.strip().split("\n")
    violations = []
    for line in lines:
        if not line:
            continue
        # Skip __pycache__ and test files
        if "__pycache__" in line or "/tests/" in line:
            continue
        if not _is_allowed(line):
            violations.append(line)

    assert not violations, (
        "Private getattr reach-through found in domain/application/infrastructure:\n"
        + "\n".join(f"  {v}" for v in violations)
        + "\n\nFix: add a public property/accessor on the owning class and "
        "update the call site to use it."
    )
