# Quick Reference: Parallel Testing Implementation Guide

## 1. Parallel Testing Commands

### Run Unit Tests in Parallel
```bash
pytest brokers/dhan/tests/unit/ -v -n auto --dist=loadscope
```

### Run Analytics Tests in Parallel
```bash
pytest analytics/tests/ -v -n auto --dist=loadscope
```

### Run Chaos Tests in Parallel
```bash
pytest tests/chaos/ -v -n auto --dist=loadscope
```

### Run Tests/Integration Tests in Parallel
```bash
pytest tests/integration/ -v -n auto --dist=loadscope
```

### Run Broker Common Tests in Parallel
```bash
pytest brokers/common/ -v -n auto --dist=loadscope
```

### Run All Parallel-Safe Tests
```bash
pytest brokers/dhan/tests/unit/ analytics/tests/ tests/chaos/ brokers/common/ \
  -v -n auto --dist=loadscope
```

## 2. Sequential Testing Commands

### Run Integration Tests (Sequential)
```bash
pytest brokers/dhan/tests/integration/ -v
```

### Run E2E Tests (Sequential)
```bash
pytest tests/e2e/ -v
```

### Run All Tests
```bash
pytest brokers/dhan/tests/unit/ analytics/tests/ tests/chaos/ brokers/common/ \
  tests/integration/ tests/e2e/ -v
```

## 3. CI/CD Pipeline Configuration

### GitHub Actions Workflow
```yaml
name: CI Parallel Testing

jobs:
  unit-tests-parallel:
    name: Unit Tests (Parallel)
    runs-on: ubuntu-latest
    timeout-minutes: 15
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"
          cache: pip
      - name: Install dependencies
        run: pip install -e ".[dev]"
      - name: Run unit tests in parallel
        run: |
          pytest brokers/dhan/tests/unit/ analytics/tests/ tests/chaos/ brokers/common/ \
            -v -n auto --dist=loadscope

  integration-tests-sequential:
    name: Integration Tests (Sequential)
    runs-on: ubuntu-latest
    timeout-minutes: 30
    needs: unit-tests-parallel
    if: github.event_name == 'push' && (github.ref == 'refs/heads/main')
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"
          cache: pip
      - name: Install dependencies
        run: pip install -e ".[dev]"
      - name: Run integration tests sequentially
        env:
          DHAN_INTEGRATION: "1"
        run: |
          pytest brokers/dhan/tests/integration/ tests/integration/ tests/e2e/ \
            -v
```

## 4. Test Markers and Categories

### Unit Tests (Parallel Safe)
```bash
pytest -m "unit" -v -n auto --dist=loadscope
```

### Analytics Tests (Parallel Safe)
```bash
pytest -m "not integration and not sandbox and not live_readonly" analytics/tests/ -v -n auto
```

### Chaos Tests (Parallel Safe)
```bash
pytest -m "chaos" -v -n auto --dist=loadscope
```

### Integration Tests (Sequential Required)
```bash
pytest -m "integration" -v
```

### Live Tests (Sequential Required)
```bash
pytest -m "live_readonly" -v
```

## 5. Test Isolation Configuration

### pytest.ini Configuration
```ini
[tool.pytest.ini_options]
minversion = "7.0"
testpaths = ["tests", "brokers", "analytics", "cli"]
markers = [
    "unit: module-owned unit tests",
    "contract: broker/module contract tests",
    "dhan: DhanHQ integration tests",
    "integration: tests that call external broker APIs",
    "sandbox: sandbox tests that may place and cancel orders",
    "live_readonly: live tests that must only read from real endpoints",
    "performance: latency and throughput benchmarks",
    "upstox: Upstox-specific unit tests",
    "upstox_integration: Upstox integration tests (gated by UPSTOX_INTEGRATION=1)",
    "upstox_sandbox: sandbox tests that may place and cancel orders",
    "upstox_live_readonly: live tests that must only read from real endpoints",
    "upstox_sdk_compat: SDK compatibility tests",
    "stress: long-running concurrency stress tests",
    "pre_prod: tests required on pre-prod gate (run only when PRE_PROD_GATE=1)",
]
asyncio_mode = "auto"
asyncio_default_fixture_loop_scope = "function"
addopts = [
    "-ra",
    "--strict-markers",
    "--tb=short",
    "-n auto",
    "--dist=loadscope",
]
```

## 6. Environment Variables

### Required for Integration Tests
```bash
export DHAN_INTEGRATION=1
```

### Optional for Live Tests
```bash
export DHAN_CLIENT_ID="your_client_id"
export DHAN_ACCESS_TOKEN="your_access_token"
```

## 7. Test Performance Monitoring

### Monitor Parallel Test Execution
```bash
# Monitor CPU usage during parallel execution
watch -n 5 "ps aux | grep pytest | grep -v grep"

# Monitor memory usage during parallel execution
watch -n 5 "free -h"

# Monitor network usage during parallel execution
watch -n 5 "netstat -tuln | grep :80"
```

### Test Execution Time Tracking
```bash
# Run tests with timing
pytest brokers/dhan/tests/unit/ -v -n auto --dist=loadscope --tb=short --timeout=300

# Capture test execution time
pytest brokers/dhan/tests/unit/ -v -n auto --dist=loadscope --tb=short --timeout=300 2>&1 | tee test_execution_time.log
```

## 8. Test Quality Assurance

### Test Coverage Reporting
```bash
# Generate coverage report
pytest brokers/dhan/tests/unit/ -v -n auto --dist=loadscope --cov=brokers --cov-report=html --cov-report=term-missing
```

### Test Flakiness Detection
```bash
# Run tests multiple times to detect flakiness
for i in {1..5}; do
    echo "Run $i:"
    pytest brokers/dhan/tests/unit/ -v -n auto --dist=loadscope --tb=short
    echo "---"
done
```

## 9. Common Issues and Solutions

### Issue: Resource Contention
**Solution**: Implement test isolation and resource cleanup

### Issue: Rate Limiting
**Solution**: Implement test throttling and mock external dependencies

### Issue: Test Flakiness
**Solution**: Implement test isolation and proper cleanup

### Issue: Memory Usage
**Solution**: Monitor memory usage and optimize test data

### Issue: Network Connectivity
**Solution**: Implement retry logic and mock external dependencies

## 10. Best Practices

### Parallel Testing Best Practices
1. **Use test isolation**: Ensure tests don't share state
2. **Implement resource cleanup**: Clean up resources after each test
3. **Monitor resource usage**: Monitor CPU, memory, and network usage
4. **Implement rate limiting**: Limit external API calls
5. **Use proper test markers**: Mark tests as parallel safe or sequential required

### Sequential Testing Best Practices
1. **Run in CI/CD pipeline**: Use sequential execution in CI/CD
2. **Implement proper environment setup**: Set up environment variables
3. **Monitor external dependencies**: Monitor external API calls
4. **Implement proper cleanup**: Clean up resources after each test
5. **Use proper test markers**: Mark tests as sequential required

## 11. Quick Start Checklist

### Step 1: Install Dependencies
```bash
pip install -e ".[dev]"
pip install pytest-xdist
```

### Step 2: Run Unit Tests in Parallel
```bash
pytest brokers/dhan/tests/unit/ -v -n auto --dist=loadscope
```

### Step 3: Run Analytics Tests in Parallel
```bash
pytest analytics/tests/ -v -n auto --dist=loadscope
```

### Step 4: Run Chaos Tests in Parallel
```bash
pytest tests/chaos/ -v -n auto --dist=loadscope
```

### Step 5: Run Integration Tests (Sequential)
```bash
pytest brokers/dhan/tests/integration/ -v
```

### Step 6: Run E2E Tests (Sequential)
```bash
pytest tests/e2e/ -v
```

### Step 7: Run All Tests
```bash
pytest brokers/dhan/tests/unit/ analytics/tests/ tests/chaos/ brokers/common/ \
  tests/integration/ tests/e2e/ -v
```

## 12. Troubleshooting

### Common Issues and Solutions

#### Issue: "Too many open files"
**Solution**: Increase file descriptor limit
```bash
sudo ulimit -n 65536
```

#### Issue: "Connection refused"
**Solution**: Check if external services are running

#### Issue: "Memory error"
**Solution**: Monitor memory usage and optimize test data

#### Issue: "Timeout error"
**Solution**: Increase timeout or implement retry logic

#### Issue: "Rate limit exceeded"
**Solution**: Implement rate limiting or mock external dependencies

This quick reference guide provides a comprehensive overview of implementing parallel testing in TradeXV2, with clear commands, configurations, and best practices for maximizing test execution speed while maintaining test reliability and coverage.