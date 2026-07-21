# Test Preserve List — Money Safety & Contracts

**Do not DELETE or weaken without an equivalent behavioral replacement.**

## Broker contracts

- `tests/integration/brokers/dhan/contract/test_broker_contract.py`
- `tests/integration/brokers/upstox/contract/test_broker_contract.py`
- `tests/integration/brokers/upstox/contract/test_upstox_contract.py`
- `tests/unit/brokers/paper/contract/**`
- `tests/unit/brokers/common/contracts/**`

## Regression manifests (live behavioral + coverage gates)

- `tests/integration/brokers/dhan/regression/manifest.py` (live cases only)
- `tests/integration/brokers/upstox/regression/manifest.py` (live cases only)
- `tests/integration/brokers/dhan/regression/test_coverage_manifest.py`
- `tests/integration/brokers/upstox/regression/test_coverage_manifest.py`

## Money safety

- `tests/integration/test_risk_deny_never_hits_venue.py`
- `tests/integration/test_kill_switch_atomic_flip.py`
- `tests/integration/test_idempotent_place.py`
- `tests/integration/test_cancel_verification.py`
- `tests/component/oms/test_money_safety_invariants.py`
- `tests/component/oms/test_capital_provider_fail_closed.py`
- `tests/component/oms/test_live_path_risk_gate_and_capital.py`
- `tests/component/oms/test_order_lifecycle_end_to_end.py`
- `tests/integration/test_parity_gate.py`
- `tests/integration/test_execution_parity.py`
- `tests/chaos/test_oms_lock_survives_concurrent_fills.py`
- `tests/chaos/test_reconciliation_failures.py`

## Certification & golden contracts

- `tests/unit/brokers/certification/**`
- `tests/integration/capability/test_capability_certification.py`
- `tests/integration/brokers/certification/test_e2e_paper_trading_os.py`
- `tests/integration/brokers/test_certification_live_probes.py`
- `tests/chaos/test_recovery_certification.py`
- `tests/unit/brokers/common/test_acl.py`
- `tests/unit/brokers/common/test_wire_base.py`
- `tests/unit/brokers/common/test_status_mapping.py`
- `tests/unit/domain/test_parsing.py`
- `tests/e2e/test_market_data_to_order_flow.py`

## Live read surfaces

- `tests/integration/brokers/dhan/test_live_read_surface_suite.py`
- `tests/integration/brokers/upstox/test_live_read_surface_suite.py`
