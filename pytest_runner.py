import subprocess
import sys
import os

os.chdir("/Users/apple/Downloads/Trade_XV2")

# Run replay tests
result = subprocess.run(
    [sys.executable, "-m", "pytest", "tests/unit/analytics/test_replay.py", "-x", "--tb=short", "-q"],
    capture_output=True, text=True, timeout=120
)
print("=== test_replay.py ===")
print(result.stdout[-3000:])
if result.returncode != 0:
    print("FAILED")
    print("STDERR:", result.stderr[-1000:])
else:
    print("PASSED")
