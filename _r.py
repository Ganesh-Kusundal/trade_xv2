#!/usr/bin/env python3
import subprocess, sys
r = subprocess.run(
    [sys.executable, "-m", "pytest",
     "tests/unit/brokers/cli/test_cli_history_batch.py",
     "-v", "--tb=short"],
    capture_output=True, text=True
)
with open("/tmp/pytest_out.txt", "w") as f:
    f.write(r.stdout)
    f.write(r.stderr)
    f.write(f"\n--- exit code: {r.returncode} ---\n")
print(r.returncode)
