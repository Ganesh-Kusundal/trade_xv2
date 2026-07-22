"""Ban external Trade_J DuckDB sync references from datalake/."""

from __future__ import annotations

from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
DATALAKE_ROOT = REPO_ROOT / "src" / "datalake"

# One-time migration tools may mention the legacy source name.
_EXCLUDE = {
    DATALAKE_ROOT / "ingestion" / "converter.py",
    DATALAKE_ROOT / "migrate_options.py",
}

_SYNC_BANNED = (
    "TRADE_J_DUCKDB",
    "rolling_option_bars",
)


@pytest.mark.architecture
def test_no_trade_j_sync_in_datalake() -> None:
    violations: list[str] = []
    for path in sorted(DATALAKE_ROOT.rglob("*.py")):
        if path in _EXCLUDE:
            continue
        text = path.read_text(encoding="utf-8")
        rel = path.relative_to(REPO_ROOT)
        for token in _SYNC_BANNED:
            if token in text:
                violations.append(f"{rel}: contains {token!r}")
    assert not violations, "Trade_J sync references in datalake:\n" + "\n".join(violations)
