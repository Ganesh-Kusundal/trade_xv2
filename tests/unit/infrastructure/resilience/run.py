"""Optional runner for resilience unit tests (no brokers.common dependency)."""

from __future__ import annotations

import sys
from collections.abc import Iterable
from pathlib import Path


def run(pytest_args: Iterable[str] | None = None) -> int:
    import pytest

    root = Path(__file__).resolve().parent
    args = [str(root), "-q"]
    if pytest_args:
        args.extend(list(pytest_args))
    return int(pytest.main(args))


if __name__ == "__main__":
    raise SystemExit(run(sys.argv[1:]))
