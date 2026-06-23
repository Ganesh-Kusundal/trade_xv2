#!/usr/bin/env python3
"""Generate a module dependency graph for the TradeXV2 codebase.

Produces:
  (1) A text-based DOT graph of module dependencies
  (2) A coupling metrics table (Ca, Ce, I) for each top-level module

Usage:
    python scripts/generate_dependency_graph.py
    python scripts/generate_dependency_graph.py --format dot  > graph.dot
    python scripts/generate_dependency_graph.py --format json > graph.json
    python scripts/generate_dependency_graph.py --format table
"""
from __future__ import annotations

import argparse
import ast
import json
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent

# Top-level modules to track
MODULES = [
    "domain",
    "infrastructure",
    "brokers/common",
    "brokers/dhan",
    "brokers/upstox",
    "brokers/paper",
    "datalake",
    "analytics",
    "cli",
]

# Map sub-packages to their parent module for coarse-grained grouping.
SUB_TO_MODULE: dict[str, str] = {}
for m in MODULES:
    for py in (ROOT / m).rglob("*.py"):
        try:
            rel = str(py.relative_to(ROOT).with_suffix(""))
            SUB_TO_MODULE[rel.replace("/", ".")] = m
        except Exception:
            pass
    # Also register the module itself
    SUB_TO_MODULE[m.replace("/", ".")] = m


def _module_of(import_path: str) -> str | None:
    """Map an import string to the top-level module it belongs to."""
    for mod in sorted(MODULES, key=len, reverse=True):
        dotted = mod.replace("/", ".").replace("-", "_")
        if import_path == dotted or import_path.startswith(dotted + "."):
            return mod
    return None


def _build_graph() -> dict[str, set[str]]:
    """Build adjacency map: {module: {imported_modules}}."""
    graph: dict[str, set[str]] = defaultdict(set)

    for py_file in ROOT.rglob("*.py"):
        if "__pycache__" in str(py_file):
            continue
        if ".mypy_cache" in str(py_file):
            continue

        rel_path = str(py_file.relative_to(ROOT).with_suffix("")).replace("/", ".")
        source_module = _module_of(rel_path)
        if source_module is None:
            continue

        try:
            tree = ast.parse(py_file.read_text(encoding="utf-8"))
        except (SyntaxError, UnicodeDecodeError):
            continue

        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    target = _module_of(alias.name)
                    if target and target != source_module:
                        graph[source_module].add(target)
            elif isinstance(node, ast.ImportFrom):
                if node.module:
                    target = _module_of(node.module)
                    if target and target != source_module:
                        graph[source_module].add(target)

    return {k: v for k, v in sorted(graph.items())}


def _compute_metrics(graph: dict[str, set[str]]) -> list[dict[str, Any]]:
    """Compute Ca, Ce, I for each module."""
    all_modules = set(graph.keys()) | {m for v in graph.values() for m in v}

    rows: list[dict[str, Any]] = []
    for mod in sorted(all_modules):
        ce = len(graph.get(mod, set()))  # outgoing
        ca = sum(1 for deps in graph.values() if mod in deps)  # incoming
        stability = ce / (ca + ce) if (ca + ce) > 0 else 0.0

        risk = "🟢 Stable"
        if stability > 0.7:
            risk = "🔴 Unstable"
        elif stability > 0.5:
            risk = "🟠 Volatile"
        elif stability > 0.3:
            risk = "🟡 Moderate"

        rows.append({
            "module": mod,
            "Ca": ca,
            "Ce": ce,
            "I": round(stability, 2),
            "risk": risk,
            "depends_on": sorted(graph.get(mod, set())),
        })

    return rows


def output_dot(graph: dict[str, set[str]]) -> str:
    """Generate DOT format."""
    lines = ["digraph TradeXV2 {", "  rankdir=BT;", '  node [shape=box, style=filled, fillcolor="#f0f0f0"];']
    for mod in sorted(set(graph.keys()) | {m for v in graph.values() for m in v}):
        lines.append(f'  "{mod}";')
    for mod, deps in sorted(graph.items()):
        for dep in sorted(deps):
            lines.append(f'  "{mod}" -> "{dep}";')
    lines.append("}")
    return "\n".join(lines)


def output_table(metrics: list[dict[str, Any]]) -> str:
    """Generate Markdown table."""
    lines = [
        "| Module | Ca (Incoming) | Ce (Outgoing) | I (Instability) | Risk |",
        "|--------|:---:|:---:|:---:|:---:|",
    ]
    for r in metrics:
        lines.append(f"| `{r['module']}` | {r['Ca']} | {r['Ce']} | {r['I']} | {r['risk']} |")
    return "\n".join(lines)


def output_json(metrics: list[dict[str, Any]]) -> str:
    """Generate JSON."""
    return json.dumps(metrics, indent=2)


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate module dependency graph.")
    parser.add_argument("--format", choices=["dot", "table", "json"], default="table")
    args = parser.parse_args()

    graph = _build_graph()
    metrics = _compute_metrics(graph)

    if args.format == "dot":
        print(output_dot(graph))
    elif args.format == "json":
        print(output_json(metrics))
    else:
        print(output_table(metrics))
        print()
        # Also print DOT for visualization
        print("### Dependency Graph (DOT):")
        print("```dot")
        print(output_dot(graph))
        print("```")


if __name__ == "__main__":
    main()
