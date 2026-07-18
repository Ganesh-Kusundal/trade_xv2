"""runtime.factory — ADR-017 composition root facade."""

from __future__ import annotations

import pytest

from runtime.factory import build, build_from_broker_service


def test_build_requires_broker_service() -> None:
    with pytest.raises(ValueError, match="broker_service is required"):
        build(None)  # type: ignore[arg-type]
