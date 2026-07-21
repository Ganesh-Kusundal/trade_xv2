#!/usr/bin/env python3
"""REF-9 migration script: rewrite `from domain import X` and
`from domain.types import X` to canonical submodule paths."""

import ast
import re
import sys
from pathlib import Path

SRC = Path("src")

# Canonical mapping: symbol → owning submodule
SYMBOL_TO_MODULE = {
    # domain.capabilities
    "Capability": "domain.capabilities",
    "ConnectionStatus": "domain.capabilities",
    # domain.entities
    "Balance": "domain.entities",
    "ConditionalAlert": "domain.entities",
    "ConditionalAlertRequest": "domain.entities",
    "DepthLevel": "domain.entities",
    "FundLimits": "domain.entities",
    "FutureChain": "domain.entities",
    "FutureContract": "domain.entities",
    "Holding": "domain.entities",
    "Instrument": "domain.entities",
    "InstrumentRecord": "domain.entities",
    "MarketDepth": "domain.entities",
    "MarketIntelligenceSnapshot": "domain.entities",
    "OptionChain": "domain.entities",
    "OptionContract": "domain.entities",
    "OptionLeg": "domain.entities",
    "OptionStrike": "domain.entities",
    "Order": "domain.entities",
    "OrderResponse": "domain.entities",
    "PnlExitPolicy": "domain.entities",
    "PnlExitResult": "domain.entities",
    "Position": "domain.entities",
    "Quote": "domain.entities",
    "Trade": "domain.entities",
    # domain.enums
    "OrderStatus": "domain.enums",
    "OrderType": "domain.enums",
    "ProductType": "domain.enums",
    "Side": "domain.enums",
    "Validity": "domain.enums",
    # domain.exceptions
    "TradeXV2RecoverableError": "domain.exceptions",
    # domain.executions
    "Execution": "domain.executions.execution",
    "GatewayResult": "domain.executions.result",
    "ResultMetadata": "domain.executions.result",
    # domain.extensions
    "Extension": "domain.extensions",
    "ExtensionRegistry": "domain.extensions",
    # domain.instruments
    "Subscription": "domain.instruments.subscription",
    # domain.market_enums
    "Exchange": "domain.market_enums",
    "ExchangeSegment": "domain.market_enums",
    "InstrumentType": "domain.market_enums",
    "OptionType": "domain.market_enums",
    # domain.orders.requests
    "ModifyOrderRequest": "domain.orders.requests",
    "OrderPreview": "domain.orders.requests",
    "OrderRequest": "domain.orders.requests",
    "SliceOrderRequest": "domain.orders.requests",
    # domain.portfolio
    "Portfolio": "domain.portfolio.portfolio",
    # domain.ports
    "BootstrapResult": "domain.ports.bootstrap",
    "BootstrapStatus": "domain.ports.bootstrap",
    "BrokerAdapter": "domain.ports.broker_adapter",
    # domain.providers
    "DataProvider": "domain.providers",
    "ExecutionProvider": "domain.providers",
    "ProviderRegistry": "domain.providers",
    "SubscriptionHandle": "domain.providers",
    # domain.reconciliation
    "DriftItem": "domain.reconciliation",
    "ReconciliationReport": "domain.reconciliation",
    # domain.risk.policy
    "ConcentrationLimit": "domain.risk.policy",
    "DailyLossCircuitBreaker": "domain.risk.policy",
    "GrossExposureLimit": "domain.risk.policy",
    "KillSwitch": "domain.risk.policy",
    "OrderNotionalLimit": "domain.risk.policy",
    "RiskGate": "domain.risk.policy",
    "RiskResult": "domain.risk.policy",
    # domain.universe
    "Session": "domain.universe",
    "Universe": "domain.universe",
    # domain.value_objects
    "ExtensionInfo": "domain.value_objects",
    "InstrumentState": "domain.value_objects",
    "Money": "domain.value_objects",
    "SubscriptionState": "domain.value_objects",
    "TickSize": "domain.value_objects",
    # domain.types extras (from types.py facade)
    "ORDER_STATUS_TRANSITIONS": "domain.entities.order_lifecycle",
    "POSITION_STATE_TRANSITIONS": "domain.entities.position",
    "PositionState": "domain.entities.position",
}

# Symbols we should NOT touch (already at canonical path or special)
SKIP_MODULES = {"domain.enums", "domain.entities", "domain.market_enums",
                "domain.capabilities", "domain.exceptions", "domain.extensions",
                "domain.providers", "domain.reconciliation", "domain.universe",
                "domain.value_objects", "domain.risk.policy", "domain.orders.requests",
                "domain.portfolio.portfolio", "domain.ports.bootstrap",
                "domain.ports.broker_adapter", "domain.instruments.subscription",
                "domain.executions.execution", "domain.executions.result",
                "domain.entities.order_lifecycle", "domain.entities.position",
                "domain.candles.historical", "domain.constants",
                "domain.runtime_hooks", "domain.portfolio.portfolio",
                "domain.portfolio", "domain.portfolio.holdings",
                "domain.portfolio.balance", "domain.portfolio.positions",
                "domain.portfolio.trades", "domain.portfolio.portfolio",
                "domain.portfolio.pnl", "domain.portfolio.reports",
                "domain.portfolio", "domain.portfolio.portfolio",
                "domain.portfolio", "domain.portfolio.portfolio",
                "domain.portfolio", "domain.portfolio.portfolio",
                "domain.portfolio", "domain.portfolio.portfolio",
                }


def rewrite_file(filepath: Path) -> list[str]:
    """Rewrite domain facade imports in a single file. Returns list of issues."""
    issues = []
    try:
        text = filepath.read_text()
    except Exception as e:
        issues.append(f"  READ ERROR: {e}")
        return issues

    lines = text.split("\n")
    new_lines = []
    i = 0

    while i < len(lines):
        line = lines[i]
        stripped = line.lstrip()
        indent = line[: len(line) - len(stripped)]

        # Match `from domain import ...` (NOT `from domain.something import ...`)
        m_from_domain = re.match(
            r'^(\s*)from\s+domain\s+import\s+(.+)$', line
        )
        # Match `from domain.types import ...`
        m_from_types = re.match(
            r'^(\s*)from\s+domain\.types\s+import\s+(.+)$', line
        )

        if m_from_domain:
            imp_indent = m_from_domain.group(1)
            imp_body = m_from_domain.group(2)

            # Check if it's `from domain import __version__` — skip
            if imp_body.strip() == "__version__":
                new_lines.append(line)
                i += 1
                continue

            # Check if multi-line (ends with `\` or contains unmatched parens)
            full_import = imp_body
            while i + 1 < len(lines) and (
                full_import.rstrip().endswith("\\")
                or full_import.count("(") > full_import.count(")")
            ):
                i += 1
                full_import += "\n" + lines[i]

            # Parse the import names
            names = _parse_import_names(full_import)
            if not names:
                issues.append(f"  {filepath}:{i+1} — could not parse: {full_import.strip()}")
                new_lines.append(line)
                i += 1
                continue

            # Group by canonical module
            by_module: dict[str, list[tuple[str, str | None]]] = {}
            unknown = []
            for name, alias in names:
                if name == "__version__":
                    by_module.setdefault("domain", []).append((name, alias))
                    continue
                mod = SYMBOL_TO_MODULE.get(name)
                if mod:
                    by_module.setdefault(mod, []).append((name, alias))
                else:
                    unknown.append((name, alias))

            if unknown:
                for name, alias in unknown:
                    issues.append(f"  UNKNOWN SYMBOL: {name} in {filepath}:{i+1}")

            # Emit new import lines
            for mod, syms in by_module.items():
                parts = []
                for name, alias in syms:
                    if alias:
                        parts.append(f"{name} as {alias}")
                    else:
                        parts.append(name)
                if len(parts) == 1:
                    new_lines.append(f"{indent}from {mod} import {parts[0]}")
                elif len(parts) <= 3:
                    new_lines.append(f"{indent}from {mod} import {', '.join(parts)}")
                else:
                    # Multi-line import
                    joined = ",\n".join(parts)
                    new_lines.append(f"{indent}from {mod} import (")
                    for p in parts:
                        new_lines.append(f"{indent}    {p},")
                    new_lines.append(f"{indent})")

        elif m_from_types:
            imp_indent = m_from_types.group(1)
            imp_body = m_from_types.group(2)

            full_import = imp_body
            while i + 1 < len(lines) and (
                full_import.rstrip().endswith("\\")
                or full_import.count("(") > full_import.count(")")
            ):
                i += 1
                full_import += "\n" + lines[i]

            names = _parse_import_names(full_import)
            if not names:
                issues.append(f"  {filepath}:{i+1} — could not parse types: {full_import.strip()}")
                new_lines.append(line)
                i += 1
                continue

            by_module: dict[str, list[tuple[str, str | None]]] = {}
            unknown = []
            for name, alias in names:
                mod = SYMBOL_TO_MODULE.get(name)
                if mod:
                    by_module.setdefault(mod, []).append((name, alias))
                else:
                    unknown.append((name, alias))

            if unknown:
                for name, alias in unknown:
                    issues.append(f"  UNKNOWN TYPES SYMBOL: {name} in {filepath}:{i+1}")

            for mod, syms in by_module.items():
                parts = []
                for name, alias in syms:
                    if alias:
                        parts.append(f"{name} as {alias}")
                    else:
                        parts.append(name)
                if len(parts) == 1:
                    new_lines.append(f"{indent}from {mod} import {parts[0]}")
                elif len(parts) <= 3:
                    new_lines.append(f"{indent}from {mod} import {', '.join(parts)}")
                else:
                    new_lines.append(f"{indent}from {mod} import (")
                    for p in parts:
                        new_lines.append(f"{indent}    {p},")
                    new_lines.append(f"{indent})")

        else:
            new_lines.append(line)

        i += 1

    new_text = "\n".join(new_lines)
    if new_text != text:
        filepath.write_text(new_text)
        issues.insert(0, f"  REWRITTEN: {filepath}")

    return issues


def _parse_import_names(body: str) -> list[tuple[str, str | None]]:
    """Parse 'X, Y as Z, \\'s multiline' into [(name, alias), ...]."""
    body = body.replace("\\\n", "").strip()
    # Remove outer parens if present
    if body.startswith("(") and body.endswith(")"):
        body = body[1:-1]
    result = []
    for part in body.split(","):
        part = part.strip()
        if not part:
            continue
        if " as " in part:
            name, alias = part.split(" as ", 1)
            result.append((name.strip(), alias.strip()))
        else:
            result.append((part.strip(), None))
    return result


def main():
    all_issues = []
    files_changed = 0

    for py in sorted(SRC.rglob("*.py")):
        if "__pycache__" in str(py):
            continue
        # Skip domain/__init__.py and domain/types.py (we handle those separately)
        if py.name == "__init__.py" and py.parent.name == "domain":
            continue
        if py.name == "types.py" and py.parent.name == "domain":
            continue

        issues = rewrite_file(py)
        if issues:
            all_issues.extend(issues)
            if any("REWRITTEN" in x for x in issues):
                files_changed += 1

    print(f"\nFiles rewritten: {files_changed}")
    if all_issues:
        print("\nIssues:")
        for issue in all_issues:
            print(issue)
    else:
        print("No issues found.")


if __name__ == "__main__":
    main()
