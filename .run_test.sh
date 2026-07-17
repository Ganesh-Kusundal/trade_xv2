.venv/bin/pytest tests/unit/brokers/cli/test_cli_history_batch.py -v --tb=short > /tmp/pytest_out.txt 2>&1
echo "exit=$?" >> /tmp/pytest_out.txt
