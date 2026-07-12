#!/bin/bash
cd /Users/apple/Downloads/Trade_XV2
python verify_decomposition.py
echo "---"
python -m pytest tests/unit/analytics/test_replay.py -x --tb=short -q 2>&1 | tail -30
echo "---"
python -m pytest tests/unit/analytics/replay/ -x --tb=short -q 2>&1 | tail -30
