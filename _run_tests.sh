#!/bin/bash
cd /Users/apple/Downloads/Trade_XV2
echo "=== TESTS ==="
.venv/bin/pytest tests/unit/brokers/services/ tests/integration/brokers/test_history_chunking_e2e.py tests/unit/brokers/cli/test_cli_history_batch.py -v --tb=short
echo ""
echo "=== IMPORTS ==="
.venv/bin/python -c "from brokers.services import get_history_batch, fetch_history, fetch_history_batch; print('imports OK')"
