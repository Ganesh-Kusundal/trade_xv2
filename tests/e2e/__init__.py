"""E2E tests for TradeXV2.

These tests require real broker credentials and should NOT run in CI.
Mark with @pytest.mark.real_broker to skip in automated tests.

Usage:
    # Run all e2e tests (requires real credentials)
    ./venv/bin/python -m pytest tests/e2e/ -v -k real_broker
    
    # Run specific test file
    ./venv/bin/python -m pytest tests/e2e/test_cli_real_data.py -v
"""
