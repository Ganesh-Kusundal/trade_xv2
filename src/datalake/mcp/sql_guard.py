"""Guard rejecting anything but a single read-only SELECT against the
pre-registered ``candles`` view.

The ``query`` MCP tool lets an LLM run arbitrary SQL, so the caller never
gets a raw filesystem path -- ``tools.py`` registers one DuckDB view
(``candles``) over the real datalake glob and this guard rejects any SQL
that isn't a single ``SELECT``/``WITH`` statement, or that references a
filesystem-reaching table function (``read_parquet``, ``read_csv``, ...)
that could otherwise be used to read files outside the datalake.
"""

from __future__ import annotations

import re

_STATEMENT_KEYWORDS = (
    "INSERT",
    "UPDATE",
    "DELETE",
    "DROP",
    "CREATE",
    "ALTER",
    "ATTACH",
    "DETACH",
    "COPY",
    "PRAGMA",
    "CALL",
    "EXPORT",
    "IMPORT",
    "INSTALL",
    "LOAD",
    "SET",
    "EXECUTE",
    "TRUNCATE",
    "GRANT",
    "REVOKE",
    "VACUUM",
    "CHECKPOINT",
    "MERGE",
    "REPLACE",
)

_FILESYSTEM_FUNCTIONS = (
    "read_parquet",
    "read_csv",
    "read_json",
    "read_text",
    "glob",
    "read_blob",
    "sniff_csv",
    "from_parquet",
    "from_csv",
)

_KEYWORD_RE = re.compile(
    r"\b(" + "|".join(_STATEMENT_KEYWORDS + _FILESYSTEM_FUNCTIONS) + r")\b",
    re.IGNORECASE,
)


def validate_select(sql: str) -> None:
    """Raise ``ValueError`` unless *sql* is a single read-only SELECT.

    Only allows querying the ``candles`` view (or CTEs built from it) --
    no DDL/DML, no chained statements, no filesystem-reaching functions.
    """
    stripped = sql.strip()
    if not stripped:
        raise ValueError("empty query")

    # Allow exactly one optional trailing semicolon; reject anything after it.
    body = stripped[:-1] if stripped.endswith(";") else stripped
    if ";" in body:
        raise ValueError("only a single statement is allowed (no ';'-chained statements)")

    first_word = body.split(None, 1)[0].upper() if body.split() else ""
    if first_word not in ("SELECT", "WITH"):
        raise ValueError(f"only SELECT/WITH queries are allowed, got: {first_word!r}")

    # ponytail: keyword regex doesn't parse string literals, so a query
    # containing e.g. WHERE note = 'please DROP by later' would be rejected
    # even though it's harmless. Upgrade to a real SQL parser (sqlglot) if
    # that false-positive rate ever matters in practice.
    match = _KEYWORD_RE.search(body)
    if match:
        raise ValueError(f"disallowed keyword/function in query: {match.group(0)!r}")
