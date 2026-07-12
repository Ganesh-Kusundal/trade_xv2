import subprocess
import sys

result = subprocess.run(
    [sys.executable, "-m", "pytest", 
     "tests/unit/analytics/test_replay.py", 
     "-x", "--tb=short", "-q"],
    capture_output=True, text=True, timeout=120
)
print(result.stdout[-4000:])
if result.stderr:
    print("STDERR:", result.stderr[-2000:])
sys.exit(result.returncode)
