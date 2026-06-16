# ADR-003: One Reconciliation Engine, Broker-Specific Fetch Adapters

## Context
Reconciliation logic was implemented three times: DhanReconciliationService, UpstoxReconciliationService, and the OMS ReconciliationService wrapper. Each used different data shapes (objects vs dicts) and severity vocabularies ("HIGH" vs "critical").

## Decision
- A shared `ReconciliationEngine` in `brokers/common/reconciliation/engine.py` provides the comparison algorithm
- Each broker provides a thin adapter that fetches broker state and maps to canonical Order/Position types
- Severity vocabulary is standardized: "HIGH", "MEDIUM", "LOW"
- The OMS `ReconciliationService` (ManagedService) wraps any engine for periodic execution

## Consequences
- Adding a new broker requires only a fetch adapter, not a new comparison algorithm
- Drift reports are comparable across brokers
- Auto-repair logic is centralized
