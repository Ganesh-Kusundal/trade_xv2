import subprocess
import sys

result = subprocess.run(
    [sys.executable, "-m", "pytest", "tests/unit/analytics/test_replay.py", "-x", "--tb=short"],
    capture_output=True, text=True, timeout=120
)
print(result.stdout[-4000:])
if result.returncode != 0:
    print("STDERR:", result.stderr[-2000:])
    sys.exit(1)
