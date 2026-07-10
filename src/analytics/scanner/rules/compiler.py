"""Rule compiler — converts JSON rule definitions to DuckDB SQL."""

from __future__ import annotations

import logging
import re
from typing import Any

from analytics.scanner.rules.models import ScannerRule

logger = logging.getLogger(__name__)

_LOOKAHEAD_PATTERNS = [
    re.compile(r"LEAD\s*\(", re.IGNORECASE),
    re.compile(r"UNBOUNDED\s+FOLLOWING", re.IGNORECASE),
]

_OP_MAP = {
    "=": "=", "==": "=", "!=": "!=", "<>": "<>",
    ">": ">", ">=": ">=", "<": "<", "<=": "<=",
    "like": "LIKE", "in": "IN",
}


def _resolve_value(value: Any, params: dict) -> Any:
    """Resolve a value that may contain {param} placeholders."""
    if isinstance(value, str) and value.startswith("{") and value.endswith("}"):
        key = value[1:-1]
        return params.get(key, value)
    return value


def validate_no_lookahead(sql: str) -> list[str]:
    warnings = []
    for pattern in _LOOKAHEAD_PATTERNS:
        for match in pattern.finditer(sql):
            warnings.append(f"Look-ahead: {match.group().strip()}")
    return warnings


class RuleCompiler:
    """Compiles JSON rule definitions to parameterized DuckDB SQL."""

    def compile(self, rule: ScannerRule | dict, params: dict | None = None) -> tuple[str, list]:
        if isinstance(rule, dict):
            rule = ScannerRule(**rule)

        params = params or {}
        bind_params: list = []
        ctes = []

        # 1. Build CTEs for window features
        for feature in rule.features:
            partition = f"PARTITION BY {', '.join(feature.partition_by)}" if feature.partition_by else ""
            order = f"ORDER BY {', '.join(feature.order_by)}" if feature.order_by else ""
            ctes.append(
                f"{feature.name} AS ("
                f"SELECT *, {feature.function} OVER ({partition} {order} {feature.frame}) AS {feature.name} "
                f"FROM {rule.from_table})"
            )

        source_table = rule.features[0].name if ctes else rule.from_table
        with_clause = "WITH " + ", ".join(ctes) if ctes else ""

        # 2. Build SELECT
        select_parts = []
        for col in rule.select:
            if col.expr:
                select_parts.append(f"({col.expr}) AS {col.alias}" if col.alias else col.expr)
            elif col.column:
                select_parts.append(f"{col.column} AS {col.alias}" if col.alias else col.column)

        if rule.score:
            expr = rule.score.expr
            if rule.score.normalize:
                n = rule.score.normalize
                lo, hi = n.get("min", 0), n.get("max", 100)
                expr = f"GREATEST({lo}, LEAST({hi}, ({expr} - {lo}) * 100.0 / ({hi} - {lo})))"
            select_parts.append(f"({expr}) AS score")

        if rule.reasons:
            cases = " ".join(f"WHEN {r.condition} THEN '{r.text}'" for r in rule.reasons)
            select_parts.append(f"CASE {cases} ELSE 'No signal' END AS reason")

        select_sql = ", ".join(select_parts) if select_parts else "*"

        # 3. Build WHERE with bind params
        where_parts = []
        for w in rule.where:
            val = _resolve_value(w.value, params)
            where_parts.append(f"{w.field} {_OP_MAP.get(w.op, w.op)} ?")
            bind_params.append(val)

        # 4. Post-score filters go into WHERE (not HAVING unless GROUP BY present)
        for f in rule.filters:
            where_parts.append(f"{f.field} {_OP_MAP.get(f.op, f.op)} ?")
            bind_params.append(f.value)

        where_sql = (" WHERE " + " AND ".join(where_parts)) if where_parts else ""

        # 5. ORDER BY + LIMIT
        order_parts = [f"{ob.field} {ob.direction.upper()}" for ob in rule.order_by]
        order_sql = (" ORDER BY " + ", ".join(order_parts)) if order_parts else ""
        limit_sql = f" LIMIT {rule.limit}" if rule.limit else ""

        sql = f"{with_clause}\nSELECT {select_sql}\nFROM {source_table}{where_sql}{order_sql}{limit_sql}".strip()

        warnings = validate_no_lookahead(sql)
        if warnings:
            logger.warning("Rule %s: %s", rule.name, warnings)

        return sql, bind_params
