"""Rule execution engine — runs JSON rules against DuckDB."""

from __future__ import annotations

import json
import logging
from pathlib import Path

import duckdb
import pandas as pd

from analytics.scanner.rules.compiler import RuleCompiler
from analytics.scanner.rules.models import ScannerRule

logger = logging.getLogger(__name__)

RULES_DIR = Path(__file__).parent / "rules"


class RuleEngine:
    """Executes JSON rules against the datalake.

    Usage:
        engine = RuleEngine()

        # Execute a saved rule
        df = engine.execute("volume_spike", params={"as_of_date": "2026-06-10"})

        # Execute inline rule
        df = engine.execute_rule({
            "name": "oversold_bounce",
            "from": "v_intraday_snapshot",
            "where": [{"field": "rsi_14", "op": "<", "value": 30}],
            "score": {"expr": "(30 - rsi_14) * 2 + roc_5 * 5"},
            "order_by": [{"field": "score", "direction": "DESC"}],
            "limit": 10
        })
    """

    def __init__(self, catalog_path: str | Path = "data/lake/catalog.duckdb") -> None:
        self._catalog_path = str(catalog_path)
        self._compiler = RuleCompiler()

    def _get_conn(self) -> duckdb.DuckDBPyConnection:
        from datalake.core.duckdb_utils import get_read_pool
        return get_read_pool().acquire(self._catalog_path)

    def _release_conn(self, conn) -> None:
        from datalake.core.duckdb_utils import get_read_pool
        get_read_pool().release(self._catalog_path, conn)

    def execute(
        self,
        rule_name: str,
        params: dict | None = None,
    ) -> pd.DataFrame:
        """Load a rule from JSON file and execute it.

        Args:
            rule_name: Name of the rule file (without .json extension).
            params: Runtime parameters (e.g., {"as_of_date": "2026-06-10"}).

        Returns:
            DataFrame with results.
        """
        rule_path = RULES_DIR / f"{rule_name}.json"
        if not rule_path.exists():
            raise FileNotFoundError(f"Rule not found: {rule_path}")

        with open(rule_path) as f:
            rule_dict = json.load(f)

        return self.execute_rule(rule_dict, params)

    def execute_rule(
        self,
        rule: dict | ScannerRule,
        params: dict | None = None,
    ) -> pd.DataFrame:
        """Execute an in-memory rule definition.

        Args:
            rule: Rule dict or ScannerRule instance.
            params: Runtime parameters.

        Returns:
            DataFrame with results.
        """
        sql, bind_params = self._compiler.compile(rule, params)

        logger.debug("Rule SQL: %s", sql)
        logger.debug("Bind params: %s", bind_params)

        conn = self._get_conn()
        try:
            result = conn.execute(sql, bind_params).fetchdf()
            return result
        except Exception as exc:
            logger.error("Rule execution failed: %s", exc)
            raise
        finally:
            self._release_conn(conn)

    def list_rules(self) -> list[dict]:
        """List all available JSON rules.

        Returns:
            List of rule metadata dicts.
        """
        rules = []
        for path in sorted(RULES_DIR.glob("*.json")):
            try:
                with open(path) as f:
                    rule = json.load(f)
                rules.append({
                    "name": rule.get("name", path.stem),
                    "description": rule.get("description", ""),
                    "file": str(path),
                })
            except Exception as exc:
                logger.warning("Failed to load rule %s: %s", path, exc)
        return rules

    def validate_rule(self, rule: dict | ScannerRule) -> list[str]:
        """Validate a rule definition.

        Returns:
            List of validation errors (empty if valid).
        """
        errors = []
        try:
            if isinstance(rule, dict):
                rule = ScannerRule(**rule)
        except Exception as exc:
            errors.append(f"Schema validation failed: {exc}")
            return errors

        if not rule.select and not rule.score:
            errors.append("Rule must have either 'select' or 'score'")

        if rule.score and not rule.score.expr:
            errors.append("Score must have an 'expr'")

        if rule.limit and rule.limit > 1000:
            errors.append(f"Limit {rule.limit} exceeds maximum (1000)")

        return errors
