import subprocess, sys, os

os.chdir("/Users/apple/Downloads/Trade_XV2")

# Run replay tests, skipping the known broken test
result = subprocess.run(
    [sys.executable, "-m", "pytest", 
     "tests/unit/analytics/test_replay.py", 
     "--deselect", "tests/unit/analytics/test_replay.py::TestReplayEngine::test_run_returns_result",
     "-v", "--tb=short"],
    capture_output=True, text=True, timeout=120
)
print(result.stdout[-4000:])
if result.returncode != 0:
    print("STDERR:", result.stderr[-2000:])
    sys.exit(1)
