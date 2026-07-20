"""Shared regression manifest types for live broker certification."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class RegressionCase:
    """One permanent regression assertion for a broker capability."""

    id: str
    capability: str
    tier: str
    segment: str
    description: str
    assert_fn: Callable[[Any], None]
    severity: str = "P0"
    tags: tuple[str, ...] = field(default_factory=tuple)


def manifest_ids(cases: tuple[RegressionCase, ...]) -> set[str]:
    return {c.id for c in cases}


def required_p0_capabilities(cases: tuple[RegressionCase, ...]) -> set[str]:
    return {c.capability for c in cases if c.severity == "P0"}
