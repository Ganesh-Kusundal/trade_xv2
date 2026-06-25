#!/usr/bin/env python3
"""Automated cleanup script for unused imports (F401).

This script:
1. Runs ruff to detect all unused imports
2. Categorizes them by severity and location
3. Provides a detailed report with recommendations
4. Optionally auto-fixes safe removals

Usage:
    python scripts/cleanup_unused_imports.py          # Dry run with report
    python scripts/cleanup_unused_imports.py --fix    # Auto-fix safe imports
    python scripts/cleanup_unused_imports.py --stats  # Show statistics only
"""

from __future__ import annotations

import subprocess
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any


def run_ruff_check(select: str = "F401", output_format: str = "concise") -> str:
    """Run ruff check and return output."""
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "ruff",
            "check",
            ".",
            "--select",
            select,
            "--output-format",
            output_format,
        ],
        capture_output=True,
        text=True,
        cwd=Path(__file__).parent.parent,
    )
    return result.stdout


def parse_unused_imports(output: str) -> dict[str, list[dict[str, Any]]]:
    """Parse ruff output into structured data."""
    issues_by_file = defaultdict(list)

    for line in output.strip().split("\n"):
        if not line or ":" not in line:
            continue

        # Parse: file.py:line:col: F401 `module.Class` imported but unused
        parts = line.split(":", 3)
        if len(parts) < 4:
            continue

        file_path = parts[0]
        line_num = int(parts[1])
        col_num = int(parts[2].split()[0])
        details = parts[3].strip()

        # Extract import name
        import_name = ""
        if "`" in details:
            import_name = details.split("`")[1]

        issues_by_file[file_path].append(
            {
                "line": line_num,
                "col": col_num,
                "import": import_name,
                "details": details,
            }
        )

    return dict(issues_by_file)


def categorize_files(issues: dict[str, list[dict[str, Any]]]) -> dict[str, dict[str, Any]]:
    """Categorize files by type (production, test, script, etc.)."""
    categories = {
        "production": {"count": 0, "files": [], "safe_to_auto_fix": True},
        "tests": {"count": 0, "files": [], "safe_to_auto_fix": True},
        "scripts": {"count": 0, "files": [], "safe_to_auto_fix": False},
        "temp": {"count": 0, "files": [], "safe_to_auto_fix": False},
    }

    for file_path, file_issues in issues.items():
        path = Path(file_path)

        if "temp/" in file_path or "temp_refactor/" in file_path:
            categories["temp"]["count"] += len(file_issues)
            categories["temp"]["files"].append(file_path)
        elif "tests/" in file_path or "/test_" in file_path:
            categories["tests"]["count"] += len(file_issues)
            categories["tests"]["files"].append(file_path)
        elif "scripts/" in file_path:
            categories["scripts"]["count"] += len(file_issues)
            categories["scripts"]["files"].append(file_path)
        else:
            categories["production"]["count"] += len(file_issues)
            categories["production"]["files"].append(file_path)

    return categories


def generate_report(
    issues: dict[str, list[dict[str, Any]]], categories: dict[str, dict[str, Any]]
) -> str:
    """Generate a detailed cleanup report."""
    total_issues = sum(len(v) for v in issues.values())

    report = []
    report.append("=" * 80)
    report.append("UNUSED IMPORTS CLEANUP REPORT")
    report.append("=" * 80)
    report.append(f"\nTotal unused imports: {total_issues}")
    report.append(f"Files affected: {len(issues)}")
    report.append("")

    # Category summary
    report.append("-" * 80)
    report.append("CATEGORY SUMMARY")
    report.append("-" * 80)
    for cat_name, cat_data in categories.items():
        report.append(
            f"\n{cat_name.upper()}: {cat_data['count']} issues in {len(cat_data['files'])} files"
        )
        if cat_data["safe_to_auto_fix"]:
            report.append(f"  ✓ Safe to auto-fix")
        else:
            report.append(f"  ⚠ Manual review recommended")

    # Top 10 files with most issues
    report.append("")
    report.append("-" * 80)
    report.append("TOP 10 FILES WITH MOST UNUSED IMPORTS")
    report.append("-" * 80)
    sorted_files = sorted(issues.items(), key=lambda x: len(x[1]), reverse=True)
    for file_path, file_issues in sorted_files[:10]:
        report.append(f"\n{file_path}: {len(file_issues)} issues")
        for issue in file_issues[:5]:  # Show first 5
            report.append(f"  Line {issue['line']}: {issue['import']}")
        if len(file_issues) > 5:
            report.append(f"  ... and {len(file_issues) - 5} more")

    # Detailed file listing
    report.append("")
    report.append("-" * 80)
    report.append("DETAILED FILE LISTING")
    report.append("-" * 80)
    for file_path in sorted(issues.keys()):
        file_issues = issues[file_path]
        report.append(f"\n{file_path} ({len(file_issues)} issues):")
        for issue in file_issues:
            report.append(f"  Line {issue['line']:4d}, Col {issue['col']:3d}: {issue['import']}")

    # Recommendations
    report.append("")
    report.append("-" * 80)
    report.append("RECOMMENDATIONS")
    report.append("-" * 80)
    report.append("")
    report.append("1. PRODUCTION CODE (safe to auto-fix):")
    report.append(f"   Run: ruff check . --fix --select=F401")
    report.append(f"   Files: {len(categories['production']['files'])}")
    report.append("")
    report.append("2. TEST CODE (safe to auto-fix):")
    report.append(f"   Run: ruff check . --fix --select=F401")
    report.append(f"   Files: {len(categories['tests']['files'])}")
    report.append("")
    report.append("3. SCRIPTS (manual review recommended):")
    report.append(f"   Files: {len(categories['scripts']['files'])}")
    report.append("   Review before auto-fixing - scripts may use dynamic imports")
    report.append("")
    report.append("4. TEMP/REFACTOR (manual review or delete):")
    report.append(f"   Files: {len(categories['temp']['files'])}")
    report.append("   Consider deleting these files if no longer needed")
    report.append("")
    report.append("=" * 80)

    return "\n".join(report)


def auto_fix_unused_imports(dry_run: bool = True) -> str:
    """Auto-fix unused imports using ruff."""
    cmd = [sys.executable, "-m", "ruff", "check", ".", "--fix", "--select=F401"]
    if dry_run:
        cmd.append("--diff")

    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        cwd=Path(__file__).parent.parent,
    )

    if dry_run:
        if result.stdout:
            return result.stdout
        return "No changes would be made (all F401 issues require manual review or are already ignored)"
    else:
        return result.stdout + result.stderr


def show_statistics() -> str:
    """Show statistics about unused imports."""
    result = subprocess.run(
        [sys.executable, "-m", "ruff", "check", ".", "--select=F401", "--statistics"],
        capture_output=True,
        text=True,
        cwd=Path(__file__).parent.parent,
    )
    return result.stdout


def main():
    """Main entry point."""
    import argparse

    parser = argparse.ArgumentParser(description="Cleanup unused imports")
    parser.add_argument("--fix", action="store_true", help="Auto-fix unused imports")
    parser.add_argument("--stats", action="store_true", help="Show statistics only")
    parser.add_argument("--dry-run", action="store_true", help="Show what would be fixed (default)")
    args = parser.parse_args()

    if args.stats:
        print(show_statistics())
        return

    # Parse issues
    output = run_ruff_check()
    issues = parse_unused_imports(output)

    if not issues:
        print("✓ No unused imports found!")
        return

    # Categorize
    categories = categorize_files(issues)

    # Generate report
    report = generate_report(issues, categories)
    print(report)

    # Auto-fix if requested
    if args.fix:
        print("\n" + "=" * 80)
        print("AUTO-FIXING UNUSED IMPORTS")
        print("=" * 80 + "\n")
        result = auto_fix_unused_imports(dry_run=False)
        print(result)
    else:
        print("\n" + "=" * 80)
        print("DRY RUN - To auto-fix, run:")
        print("  python scripts/cleanup_unused_imports.py --fix")
        print("  OR")
        print("  ruff check . --fix --select=F401")
        print("=" * 80)


if __name__ == "__main__":
    main()
