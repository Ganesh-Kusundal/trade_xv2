# Dependency Rules

**Version:** 1.0 (TRANS-P1-007)  
**Related:** [DEPENDENCY_GRAPH.md](./DEPENDENCY_GRAPH.md) (task DAG, package layers, parallel waves)  
**Enforcement:** `pyproject.toml` `[tool.importlinter]` + `tests/architecture/`

Run locally:

```bash
PYTHONPATH=src lint-imports --config pyproject.toml
```

---

## Layer matrix

| From ↓ / To → | domain | application | infrastructure | brokers | runtime | interface | analytics |
|---------------|--------|-------------|----------------|---------|---------|-----------|-----------|
| **domain** | ✅ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ |
| **application** | ✅ | ✅ | ❌* | ❌ | ❌ | ❌ | ❌ |
| **infrastructure** | ✅ | ❌ | ✅ | ❌** | ❌ | ❌ | ❌ |
| **brokers** | ✅ | ❌ | ❌ | ✅ | ❌ | ❌ | ❌ |
| **runtime** | ✅ | ✅ | ✅ | ✅ | ✅ | ❌ | ❌ |
| **interface** | ✅ | ✅ | ❌*** | ❌ | ✅ | ✅ | ❌ |
| **analytics** | ✅ | ❌**** | ❌ | ❌***** | ❌ | ❌ | ✅ |

\* Approved infra debt edges only (see below).  
\** Gateway factory may import brokers (composition).  
\*** UI/API use `connect` shims, not raw `infrastructure.gateway.factory`.  
\**** Analytics must not import `application.oms`.  
\***** Analytics must not import concrete broker packages.

---

## Import-linter contracts (15)

| # | Contract | Intent |
|---|----------|--------|
| 1 | Domain independence | Domain never imports outer layers |
| 2 | Infrastructure independence | Infra does not import application/UI |
| 3 | Analytics broker isolation | No `brokers.dhan/upstox/paper` in analytics |
| 4 | Analytics OMS isolation | Scanner bugs cannot touch OMS |
| 5 | Application broker isolation | OMS does not import broker wire |
| 6 | Broker common isolation | `brokers.common` broker-agnostic |
| 7 | Broker cross-import | dhan ⊥ upstox |
| 8 | Datalake analytics isolation | Research data ≠ live analytics coupling |
| 9 | Tradex broker isolation | Public SDK hides wire |
| 10 | Application infrastructure separation | App → infra forbidden (debt list) |
| 11 | CLI broker isolation | UI uses facades |
| 12 | API broker isolation | API uses tradex session |
| 13 | Tradex public API isolation | SDK surface clean |
| 14 | UI gateway factory | connect shims only |
| 15 | (additional UI/registry) | Registry composition edges |

---

## Approved application → infrastructure debt

Synced with `pyproject.toml`, `test_application_no_infra_imports.py`, and `test_dependency_graph_sync.py` (see [DEPENDENCY_GRAPH.md](./DEPENDENCY_GRAPH.md) §5):

| Source | Target | Removal target |
|--------|--------|----------------|
| `application.composer.router` | `infrastructure.observability.audit` | AuditPort (P5) |
| `application.composer.router` | `infrastructure.time.clock` | TimeService inject |
| `application.composer.gap_reconciler` | `infrastructure.time.clock` | TimeService inject |
| `application.services.download_engine` | `infrastructure.io.parquet` | Storage port |
| `application.services.historical_data` | `infrastructure.historical_data` | Wave 3 move |
| `application.services.production_readiness` | `infrastructure.security.ssl_hardening` | TLS port |
| `application.data.provenance` | `infrastructure.time.clock` | TimeService inject |
| `application.data.historical_coordinator` | `infrastructure.observability.audit` | AuditPort |
| `application.streaming.orchestrator` | `infrastructure.observability.audit` | AuditPort |
| `application.scheduling.quota_scheduler` | `infrastructure.observability.audit` | AuditPort |

**Never allowed:** `infrastructure.observability.tracing` in application (use `application.observability`).

---

## Domain broker rule

`domain` must not import `brokers.*`. Segment mapping uses:

- Protocol: `domain.market.segment_mapper.SegmentMapper`
- Registry: `domain.market.segment_registry`
- Registration: broker `__init__.py` at plugin import

Verified by `tests/architecture/test_domain_no_broker_imports.py`.

---

## CI architecture tests

| Test | Guard |
|------|-------|
| `test_domain_no_broker_imports` | No `brokers` in `src/domain` |
| `test_application_no_infra_imports` | No unapproved `infrastructure` in `src/application` |
| `test_dependency_graph_sync` | `_APPROVED_EDGES` ↔ pyproject contract #10 |
| `test_workflow_paths` | CI YAML paths exist |

Blocking per [ADR-019](./adrs/adr-019-ci-gates.md).