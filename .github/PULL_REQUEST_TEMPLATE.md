## Description

<!-- Describe what this PR changes and why. Link to relevant issues. -->

## Type of Change

- [ ] Bug fix (non-breaking change that fixes an issue)
- [ ] New feature (non-breaking change that adds functionality)
- [ ] Breaking change (fix or feature that would cause existing functionality to not work as expected)
- [ ] Performance optimization
- [ ] Refactoring (no functional change)
- [ ] Documentation update
- [ ] Test addition/improvement
- [ ] CI/CD change

## Testing

<!-- Describe the tests you ran and how to reproduce them. -->

- [ ] Unit tests pass: `pytest tests/`
- [ ] Integration tests pass (if applicable): `pytest -m integration`
- [ ] MyPy type check passes: `mypy brokers/`
- [ ] Linting passes: `ruff check .`
- [ ] Manual testing performed: <!-- describe what you tested -->

## Performance Impact (if applicable)

- [ ] No performance impact expected
- [ ] Performance improved (include benchmarks)
- [ ] Performance degraded (explain why and mitigation plan)

<!-- If performance-related, attach before/after benchmarks: -->
<!-- - Tick latency: X ms → Y ms -->
<!-- - Memory: X MB → Y MB -->
<!-- - Throughput: X ops/s → Y ops/s -->

## Quant Parity (if trading-related)

- [ ] Not applicable (non-trading change)
- [ ] Replay determinism preserved: `python scripts/verify_event_replay.py` passes
- [ ] Scanner determinism preserved: `python scripts/quant_baseline.py` passes
- [ ] PnL parity verified (include tolerance if any):

## Breaking Changes (if any)

<!-- List any breaking changes and migration steps: -->
- [ ] No breaking changes
- [ ] Breaking change: <!-- describe -->
  Migration: <!-- steps -->

## Checklist

- [ ] Code follows project style guidelines (ruff + mypy)
- [ ] Self-review completed
- [ ] Comments added for complex logic
- [ ] Documentation updated (if needed)
- [ ] No new TODOs without tracking issue
- [ ] Feature flag added (if risky change)
- [ ] Alerting/monitoring updated (if applicable)

## Screenshots / Logs (if applicable)

<!-- Attach relevant output, logs, or screenshots -->
