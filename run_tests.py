import subprocess
import sys

result = subprocess.run(
    [sys.executable, "-m", "pytest", 
     "tests/unit/brokers/cli/test_cli_history_batch.py", 
     "-v", "--tb=short"],
    capture_output=True, text=True,
    cwd="/Users/apple/Downloads/Trade_XV2"
)

output = result.stdout + result.stderr
with open("/tmp/pytest_out.txt", "w") as f:
    f.write(output)
print(f"Exit code: {result.returncode}")
print("Output written to /tmp/pytest_out.txt")
