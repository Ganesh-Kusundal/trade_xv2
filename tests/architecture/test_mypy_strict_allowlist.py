"""Verify the mypy-strict allowlist can only grow — a sentinel for CI."""


def test_allowlist_can_only_grow() -> None:
    """Allowlist must have at least 6 modules (set by REF-15)."""
    with open("mypy-strict-allowlist.txt") as f:
        lines = [l.strip() for l in f if l.strip() and not l.startswith("#")]
    assert len(lines) >= 6, f"Allowlist should have at least 6 modules, got {len(lines)}"
