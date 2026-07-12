import subprocess, sys, os

os.chdir("/Users/apple/Downloads/Trade_XV2")

tests = [
    "tests/unit/analytics/replay/test_replay_memory.py",
    "tests/unit/analytics/test_replay_equity_costs.py",
]

for t in tests:
    result = subprocess.run(
        [sys.executable, "-m", "pytest", t, "-v", "--tb=short"],
        capture_output=True, text=True, timeout=60
    )
    print(f"=== {t} ===")
    # Print last 20 lines of stdout
    lines = result.stdout.strip().split("\n")
    for line in lines[-15:]:
        print(line)
    if result.returncode != 0:
        print("FAILED")
    else:
        print("PASSED")
    print()
