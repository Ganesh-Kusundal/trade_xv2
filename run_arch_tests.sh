#!/bin/bash
cd /Users/apple/Downloads/Trade_XV2
python -m pytest tests/architecture/ -x -q --tb=no 2>&1 | tail -5
