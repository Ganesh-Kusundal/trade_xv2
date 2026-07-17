import subprocess, sys
r = subprocess.run([sys.executable, "-m", "pytest", "tests/unit/brokers/cli/test_cli_history_batch.py", "-v", "--tb=short"], capture_output=True, text=True, cwd="/Users/apple/Downloads/Trade_XV2")
open("/tmp/py_out.txt","w").write(r.stdout + r.stderr + f"\nexit={r.returncode}\n")
print(r.returncode)
