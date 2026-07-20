#!/usr/bin/env python3
"""Verify that venv/ has all dependencies from requirements.txt and pyproject.toml"""

import json
import re
import subprocess
import sys

# Read requirements.txt (optional — project uses pyproject.toml as canonical)
from pathlib import Path

req_lines: list[str] = []
_req_path = Path("requirements.txt")
if _req_path.is_file():
    req_lines = [
        line.strip()
        for line in _req_path.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.startswith("#")
    ]

# Read pyproject.toml dependencies
with open("pyproject.toml") as f:
    content = f.read()

# Extract main dependencies
deps_match = re.search(r"dependencies = \[(.*?)\]", content, re.DOTALL)
pyproject_deps = []
if deps_match:
    deps_str = deps_match.group(1)
    pyproject_deps = [
        d.strip().split(">=")[0].split("<")[0].strip("\"'")
        for d in deps_str.split("\n")
        if d.strip()
    ]

# Extract dev dependencies
dev_match = re.search(r"dev = \[(.*?)\]", content, re.DOTALL)
pyproject_dev_deps = []
if dev_match:
    dev_str = dev_match.group(1)
    pyproject_dev_deps = [
        d.strip().split(">=")[0].split("<")[0].strip("\"'")
        for d in dev_str.split("\n")
        if d.strip()
    ]

# Get installed packages
result = subprocess.run(
    [sys.executable, "-m", "pip", "list", "--format=json"], capture_output=True, text=True
)
installed = {
    pkg["name"].lower().replace("-", "_"): pkg["version"] for pkg in json.loads(result.stdout)
}

print("=" * 80)
print("DEPENDENCY VERIFICATION REPORT")
print("=" * 80)

# Check requirements.txt
print("\n📋 requirements.txt packages:")
missing_req = []
for req in req_lines:
    pkg_name = req.split(">=")[0].split("<")[0].split("==")[0].lower().strip()
    pkg_key = pkg_name.replace("-", "_")
    if pkg_key in installed:
        print(f"  ✓ {pkg_name} {installed[pkg_key]}")
    else:
        print(f"  ✗ {pkg_name} - MISSING")
        missing_req.append(pkg_name)

# Check pyproject.toml main deps
print("\n📦 pyproject.toml [project.dependencies]:")
missing_main = []
for dep in pyproject_deps:
    pkg_key = dep.lower().replace("-", "_")
    if pkg_key in installed:
        print(f"  ✓ {dep} {installed[pkg_key]}")
    else:
        print(f"  ✗ {dep} - MISSING")
        missing_main.append(dep)

# Check pyproject.toml dev deps
print("\n🔧 pyproject.toml [project.optional-dependencies] dev:")
missing_dev = []
for dep in pyproject_dev_deps:
    pkg_key = dep.lower().replace("-", "_")
    if pkg_key in installed:
        print(f"  ✓ {dep} {installed[pkg_key]}")
    else:
        print(f"  ✗ {dep} - MISSING")
        missing_dev.append(dep)

# Summary
print("\n" + "=" * 80)
all_missing = missing_req + missing_main + missing_dev
if all_missing:
    print(f"❌ MISSING {len(all_missing)} packages:")
    for pkg in set(all_missing):
        print(f"   - {pkg}")
    print("\nFix command:")
    print("  ./venv/bin/pip install -r requirements.txt")
    print('  ./venv/bin/pip install ".[dev]"')
else:
    print("✅ All dependencies are properly installed!")
print("=" * 80)
