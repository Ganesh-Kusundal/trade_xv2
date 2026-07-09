"""Datalake-local JSON rule scanner (DuckDB / catalog).

Analytics-facing scanners (MomentumScanner, scorer, etc.) live under
``analytics.scanner``. This package only exposes the SQL rule engine that
runs against datalake views and local rule JSON files under
``datalake/scanner/rules/``.
"""

from datalake.scanner.compiler import RuleCompiler
from datalake.scanner.engine import RuleEngine
from datalake.scanner.models import ScannerRule

__all__ = ["RuleCompiler", "RuleEngine", "ScannerRule"]
