#!/usr/bin/env python3
"""Extract public methods from Dhan and Upstox broker adapter modules.

Usage:
    python scripts/audit_broker_methods.py
    python scripts/audit_broker_methods.py --json
    python scripts/audit_broker_methods.py --broker dhan
"""

from __future__ import annotations

import argparse
import ast
import json
import sys
from dataclasses import dataclass, field
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))


@dataclass
class ClassMethods:
    """Public methods on a class."""

    class_name: str
    module: str
    methods: list[str] = field(default_factory=list)


@dataclass
class DomainAudit:
    """Audit result for one broker domain directory."""

    broker: str
    domain: str
    file: str
    classes: list[ClassMethods] = field(default_factory=list)


def _public_methods_from_class(node: ast.ClassDef) -> list[str]:
    methods: list[str] = []
    for item in node.body:
        if isinstance(item, ast.FunctionDef | ast.AsyncFunctionDef):
            if item.name.startswith("_"):
                continue
            methods.append(item.name)
    return sorted(methods)


def _audit_python_file(broker: str, path: Path) -> DomainAudit | None:
    try:
        source = path.read_text(encoding="utf-8")
        tree = ast.parse(source, filename=str(path))
    except (OSError, SyntaxError):
        return None

    rel = path.relative_to(PROJECT_ROOT)
    broker_root = PROJECT_ROOT / "brokers" / broker
    try:
        domain = str(rel.parent.relative_to(broker_root))
    except ValueError:
        domain = "."
    if domain == ".":
        domain = rel.parent.name if rel.parent.name != broker else "root"
    audit = DomainAudit(broker=broker, domain=domain, file=str(rel))

    for node in tree.body:
        if isinstance(node, ast.ClassDef) and not node.name.startswith("_"):
            methods = _public_methods_from_class(node)
            if methods:
                audit.classes.append(
                    ClassMethods(class_name=node.name, module=str(rel), methods=methods)
                )
    return audit if audit.classes else None


def audit_broker(broker: str) -> list[DomainAudit]:
    """Walk broker package and extract public class methods."""
    root = PROJECT_ROOT / "brokers" / broker
    if not root.exists():
        return []

    results: list[DomainAudit] = []
    for path in sorted(root.rglob("*.py")):
        if "tests" in path.parts or path.name.startswith("test_"):
            continue
        audit = _audit_python_file(broker, path)
        if audit is not None:
            results.append(audit)
    return results


def summarize(audits: list[DomainAudit]) -> dict:
    """Build JSON-serializable summary."""
    by_broker: dict[str, dict] = {}
    for audit in audits:
        broker_data = by_broker.setdefault(audit.broker, {"domains": {}, "total_methods": 0})
        domain_entry = broker_data["domains"].setdefault(audit.domain, {"files": []})
        for cls in audit.classes:
            domain_entry["files"].append(
                {
                    "file": audit.file,
                    "class": cls.class_name,
                    "methods": cls.methods,
                    "method_count": len(cls.methods),
                }
            )
            broker_data["total_methods"] += len(cls.methods)
    return by_broker


def main() -> int:
    parser = argparse.ArgumentParser(description="Audit broker adapter public methods")
    parser.add_argument("--broker", choices=["dhan", "upstox", "all"], default="all")
    parser.add_argument("--json", action="store_true", help="Output JSON")
    args = parser.parse_args()

    brokers = ["dhan", "upstox"] if args.broker == "all" else [args.broker]
    all_audits: list[DomainAudit] = []
    for broker in brokers:
        all_audits.extend(audit_broker(broker))

    data = summarize(all_audits)

    if args.json:
        print(json.dumps(data, indent=2))
        return 0

    for broker, info in data.items():
        print(f"\n{'=' * 60}")
        print(f"  {broker.upper()} — {info['total_methods']} public methods")
        print(f"{'=' * 60}")
        for domain, domain_info in sorted(info["domains"].items()):
            print(f"\n  [{domain}]")
            for file_info in domain_info["files"]:
                print(f"    {file_info['class']} ({file_info['file']})")
                for m in file_info["methods"]:
                    print(f"      - {m}()")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
