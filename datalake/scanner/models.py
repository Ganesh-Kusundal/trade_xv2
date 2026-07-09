"""Pydantic models for JSON-based scanner rules (datalake-local).

These models back the SQL rule engine under ``datalake.scanner``.
Analytics package scanners live under ``analytics.scanner`` and may keep
their own rule models; this module must not import the top-level analytics
package.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class SelectColumn(BaseModel):
    """A column in the SELECT clause."""

    column: str | None = None
    expr: str | None = None
    alias: str | None = None


class WhereCondition(BaseModel):
    """A WHERE clause condition."""

    field: str
    op: str = "="
    value: Any = None


class WindowFeature(BaseModel):
    """A window function feature (CTE)."""

    name: str
    type: str = "window"
    function: str
    partition_by: list[str] = Field(default_factory=list)
    order_by: list[str] = Field(default_factory=list)
    frame: str = "ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW"


class ScoreConfig(BaseModel):
    """Scoring configuration."""

    expr: str
    normalize: dict | None = None


class FilterCondition(BaseModel):
    """Post-score filter."""

    field: str
    op: str = ">="
    value: Any = None


class ReasonRule(BaseModel):
    """Reason text generation rule."""

    condition: str
    text: str


class OrderByClause(BaseModel):
    """ORDER BY clause."""

    field: str
    direction: str = "DESC"


class ScannerRule(BaseModel):
    """Complete scanner rule definition."""

    name: str
    version: str = "1.0"
    description: str = ""
    universe: str | None = None
    timeframe: str = "1m"

    select: list[SelectColumn] = Field(default_factory=list)
    from_table: str = Field(alias="from")
    where: list[WhereCondition] = Field(default_factory=list)
    features: list[WindowFeature] = Field(default_factory=list)
    joins: list[dict] = Field(default_factory=list)
    score: ScoreConfig | None = None
    filters: list[FilterCondition] = Field(default_factory=list)
    reasons: list[ReasonRule] = Field(default_factory=list)
    order_by: list[OrderByClause] = Field(default_factory=list)
    limit: int = 20

    model_config = {"populate_by_name": True}


__all__ = [
    "FilterCondition",
    "OrderByClause",
    "ReasonRule",
    "ScannerRule",
    "ScoreConfig",
    "SelectColumn",
    "WhereCondition",
    "WindowFeature",
]
