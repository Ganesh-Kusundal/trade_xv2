"""GOV-2: ADR-011 LOC limit enforcement."""

from pathlib import Path

MAX_LOC = 650
SRC = Path("src")


def test_no_files_exceed_loc_limit():
    violations = []
    for py in SRC.rglob("*.py"):
        loc = len(py.read_text().splitlines())
        if loc > MAX_LOC:
            violations.append(f"{py}: {loc} LOC (max {MAX_LOC})")
    assert not violations, "LOC violations:\n" + "\n".join(violations[:20])
