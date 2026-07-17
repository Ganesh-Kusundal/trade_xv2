import subprocess
import sys

for label, args in [
    ("UNIT BROKERS", [".venv/bin/pytest", "tests/unit/brokers/", "-v", "--tb=short"]),
    ("INTEGRATION BROKERS", [".venv/bin/pytest", "tests/integration/brokers/", "-v", "--tb=short"]),
]:
    print(f"\n{'='*60}")
    print(f"  {label}")
    print(f"{'='*60}")
    result = subprocess.run(args, capture_output=True, text=True, cwd="/Users/apple/Downloads/Trade_XV2")
    # Print last 100 lines of combined output
    lines = (result.stdout + result.stderr).splitlines()
    for line in lines[-100:]:
        # Strip ANSI escape codes
        import re
        clean = re.sub(r'\x1b\[[0-9;]*m', '', line)
        print(clean)
    print(f"\nReturn code: {result.returncode}")
