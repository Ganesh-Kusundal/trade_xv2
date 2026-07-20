#!/usr/bin/env python3
"""Guardrail script to detect scattered magic constants in the codebase.

This script is intended to be run as a pre-commit hook or in CI to catch:
1. Hardcoded exchange strings (NSE, BSE, MCX, etc.) outside constants module
2. Hardcoded timeout values
3. Hardcoded segment strings (NSE_EQ, BSE_FO, etc.)
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

# Patterns to detect (exchange constants, segment strings, magic timeouts)
EXCHANGE_PATTERNS = [
    (r'"NSE"', "Use domain.constants.exchanges.NSE instead of hardcoded 'NSE'"),
    (r'"BSE"', "Use domain.constants.exchanges.BSE instead of hardcoded 'BSE'"),
    (r'"MCX"', "Use domain.constants.exchanges.MCX instead of hardcoded 'MCX'"),
    (r'"NFO"', "Use domain.constants.exchanges.NFO instead of hardcoded 'NFO'"),
    (r'"BFO"', "Use domain.constants.exchanges.BFO instead of hardcoded 'BFO'"),
    (r'"CDS"', "Use domain.constants.exchanges.CDS instead of hardcoded 'CDS'"),
    (r"'NSE'", "Use domain.constants.exchanges.NSE instead of hardcoded 'NSE'"),
    (r"'BSE'", "Use domain.constants.exchanges.BSE instead of hardcoded 'BSE'"),
    (r"'MCX'", "Use domain.constants.exchanges.MCX instead of hardcoded 'MCX'"),
]

SEGMENT_PATTERNS = [
    (r'"NSE_EQ"', "Use domain.constants.exchanges.WIRE_NSE_EQ instead of hardcoded 'NSE_EQ'"),
    (r'"NSE_FO"', "Use domain.constants.exchanges.WIRE_NSE_FNO instead of hardcoded 'NSE_FO'"),
    (r'"MCX_FUT"', "Use domain.constants.exchanges for MCX_FUT mappings"),
]

# Inline timezone construction — the canonical IST lives in one place.
TIMEZONE_PATTERNS = [
    (
        r'ZoneInfo\(\s*["\']Asia/Kolkata["\']\s*\)',
        "Use domain.constants.market.IST instead of ZoneInfo('Asia/Kolkata')",
    ),
]

# Hardcoded NSE session hours — canonical in domain.market.hours (REF-2a).
MARKET_HOURS_PATTERNS = [
    (
        r"\btime\(\s*9\s*,\s*15\s*\)",
        "Use domain.market.hours.NSE_EQUITY_OPEN instead of hardcoded time(9, 15)",
    ),
    (
        r"\btime\(\s*15\s*,\s*30\s*\)",
        "Use domain.market.hours.NSE_EQUITY_CLOSE instead of hardcoded time(15, 30)",
    ),
    (
        r'"09:15:00"',
        "Use domain.market.hours.NSE_EQUITY_OPEN instead of hardcoded '09:15:00'",
    ),
]

# All pattern groups actually enforced by check_file. (SEGMENT_PATTERNS was
# previously defined but never iterated — now included.)
ALL_PATTERNS = EXCHANGE_PATTERNS + SEGMENT_PATTERNS + TIMEZONE_PATTERNS + MARKET_HOURS_PATTERNS

# Allowlist - files where these patterns are expected
ALLOWLIST = {
    "domain/constants/exchanges.py",
    "domain/constants/segments.py",
    "domain/constants/market.py",
    "domain/constants/__init__.py",
    "config/",
    "indices.py",
    "datalake/",
    "infrastructure/",
    "domain/exchange_segments.py",
    "domain/conventions.py",
    "domain/symbols.py",
    "domain/universe.py",
    "domain/exceptions.py",
    "domain/instrument_resolver.py",
    "domain/market_enums.py",
    "tradex/",
    # Analytics layer files
    "analytics/paper/",
    "analytics/core/providers.py",
    "analytics/backtest/",
    "analytics/replay/",
    "analytics/views/",
    "analytics/scanner/",
    "analytics/strategy/",
    # Domain extensions and core
    "domain/extensions/",
    "domain/options/",
    "domain/futures/",
    "domain/instruments/",
    "domain/value_objects/",
    "domain/candles/",
    "domain/portfolio/",
    "domain/market/",
    "domain/orders/",
    "domain/ports/",
    "domain/entities/",
    # Application layer
    "application/",
    # Plugins and interface layers
    "plugins/",
    "interface/",
    # Broker paper layer (synthetic data uses hardcoded exchanges)
    "brokers/paper/paper_gateway.py",
    "brokers/paper/segment_mapper.py",
    "brokers/paper/__init__.py",
    # Broker dhan layer (segment mappings and validation)
    "brokers/dhan/segments.py",
    "brokers/dhan/wire.py",
    "brokers/dhan/loader.py",
    "brokers/dhan/extended_data.py",
    "brokers/dhan/portfolio/",
    "brokers/dhan/data/",
    # Broker upstox adapter layer
    "brokers/upstox/instrument_adapter.py",
    "brokers/upstox/adapters/",
    "brokers/upstox/market_data/futures.py",
    "brokers/upstox/market_data/market_status.py",
    "brokers/upstox/instruments/",
    "brokers/upstox/mappers/",
    "brokers/upstox/orders/order_command_adapter.py",
    # Broker services and certification layers
    "brokers/services/",
    "brokers/certification/",
    # Broker session and streaming layers
    "brokers/session/",
    "brokers/dhan/websocket/",
    "brokers/dhan/identity/",
    "brokers/dhan/extensions/",
    "brokers/dhan/streaming/",
    # Broker common layer (contracts, OMS, API)
    "brokers/common/oms/",
    "brokers/common/contracts/",
    "brokers/common/api/",
    "brokers/common/usecases/",
    # Broker validation and CLI layers (legitimate exchange lists)
    "brokers/cli/",
    "brokers/common/recon_local.py",
    "brokers/dhan/symbol_validator.py",
    "brokers/dhan/extended_positions.py",
    "brokers/dhan/extended.py",
    "_test_",
    "_spec_",
}


def _docstring_spans(content: str) -> list[tuple[int, int]]:
    """Return (start, end) offsets of every triple-quoted string block.

    Matches are ignored when they fall inside one of these spans, so
    multi-line docstrings that mention e.g. ``"NSE_EQ"`` as documentation do
    not produce false positives (the previous line-based check only skipped
    triple quotes appearing on the same physical line as the match).
    """
    return [
        (m.start(), m.end()) for m in re.finditer(r'""".*?"""|\'\'\'.*?\'\'\'', content, re.DOTALL)
    ]


def check_file(filepath: Path) -> list[str]:
    """Check a single file for scattered constants."""
    errors = []
    content = filepath.read_text()

    # Skip allowlisted files
    for pattern in ALLOWLIST:
        if pattern in str(filepath):
            return errors

    doc_spans = _docstring_spans(content)

    # Check for scattered-constant patterns (excluding docstrings and comments)
    for pattern, message in ALL_PATTERNS:
        for match in re.finditer(pattern, content):
            # Skip matches inside a multi-line docstring block.
            if any(start <= match.start() < end for start, end in doc_spans):
                continue
            lineno = content[: match.start()].count("\n") + 1
            line_start = content.rfind("\n", 0, match.start()) + 1
            line = content[line_start : content.find("\n", match.start())]
            # Skip single-line comments and single-line docstrings.
            if "#" not in line and '"""' not in line and "'''" not in line:
                errors.append(f"{filepath}:{lineno}: {message}")

    return errors


def main() -> int:
    """Run the check across src/ directory."""
    src_dir = Path(__file__).parent.parent / "src"
    all_errors = []

    for py_file in src_dir.rglob("*.py"):
        errors = check_file(py_file)
        all_errors.extend(errors)

    if all_errors:
        print("Scattered constant violations found:")
        for error in all_errors[:20]:  # Limit output
            print(f"  {error}")
        print(f"\nTotal violations: {len(all_errors)}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
