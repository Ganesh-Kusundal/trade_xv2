#!/usr/bin/env python3
"""Run replay tests to verify refactoring."""
import subprocess, sys

result = subprocess.run(
    [sys.executable, "-m", "pytest", "tests/unit/analytics/test_replay.py", "-x", "--tb=short"],
    capture_output=True, text=True, timeout=120
)
print(result.stdout[-4000:])
if result.stderr:
    print("STDERR:", result.stderr[-2000:])
sys.exit(result.returncode)
