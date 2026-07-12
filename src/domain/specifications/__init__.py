"""Specifications domain — Specification ABC and concrete implementations."""

from __future__ import annotations

from domain.specifications.concrete import (
    EquitySpecification,
    FutureSpecification,
    IndexSpecification,
    OptionSpecification,
)
from domain.specifications.factory import get_specification
from domain.specifications.specification import Specification

__all__ = [
    "EquitySpecification",
    "FutureSpecification",
    "IndexSpecification",
    "OptionSpecification",
    "Specification",
    "get_specification",
]
