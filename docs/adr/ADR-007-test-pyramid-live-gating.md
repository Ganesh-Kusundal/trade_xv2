# ADR-007: Test Pyramid & Live Gating

## Status
Accepted (Phase 0)

## Context
Real broker connections are necessary for certification, but placing real orders
and hitting live endpoints in CI is unsafe and expensive.

## Decision
Full pyramid, mapped to pytest markers:

| Layer | Network | Markers |
|---|---|---|
| Unit | none | default |
| Property-based | none | `property` |
| Component | mock/double | `component` |
| Contract (per plugin) | mock/double | `contract`, `dhan`, `upstox`, `upstox_integration`, `upstox_sdk_compat` |
| Integration | mock adapter | `integration`, `oms_integration` |
| Sandbox | real (gated, self-cancelling) | `sandbox`, `upstox_sandbox`, `cli_endpoint_sandbox` |
| E2E | real (gated) | `e2e`, `live_readonly`, `upstox_live_readonly`, `off_market_safe`, `market_hours`, `cli_endpoint`, `cli_endpoint_live`, `auth_integration` |
| E2E live orders | real (gated) | `live_orders` (needs `TRADEX_LIVE_ORDERS=1`) |
| Parity / determinism | mock/replay | `paper_replay_parity`, `cross_broker_parity`, `live_backtest_parity`, `scanner_determinism`, `feature_parity` |
| Performance | bench | `performance`, `memory` |
| Stress | bench | `stress`, `slow` |
| Gating | — | `pre_prod`, `regression` |
| Mutation | — | `mutation` |

Live gating:
- `TRADEX_LIVE_TESTS=1` enables read-only live endpoints (validated by
  `CredentialValidator.broker_available(name)`).
- `TRADEX_LIVE_ORDERS=1` (separate flag) enables **guarded** real order placement:
  1-lot INTRADAY, marketable→immediate cancel, idempotency correlation id, assert
  cancel before fill assertions. Never set in CI.

New markers added in Phase 0: `live_orders`, `property`, `component`, `mutation`.

**Refreshed 2026-07-10:** the pyramid grew past Phase 0's dozen markers to
33 real markers (verified directly against `pyproject.toml`
`[tool.pytest.ini_options]`). The table above now reflects the full,
current set. The underlying *policy* — live gating via
`TRADEX_LIVE_TESTS`/`TRADEX_LIVE_ORDERS`, never real orders in CI — is
unchanged and still correctly followed; only this table was stale. Status
remains Accepted. See
`docs/architecture/trading-os/TRADING_OS_BLUEPRINT_V2_PART6.md` §3.

## Consequences
- `pytest tests/ -m "not integration and not live"` is the default safe gate.
- Real-money paths are explicit, gated, and self-cancelling.
