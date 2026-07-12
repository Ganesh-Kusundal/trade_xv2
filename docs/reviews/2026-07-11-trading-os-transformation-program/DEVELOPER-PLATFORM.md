# Developer Platform Roadmap

**Goal:** No engineer or AI agent writes ad-hoc scripts to validate functionality.

**Status (2026-07-11):** Iteration 6 — doctor JSON schema unified, `/ready` + `/readyz` gates, CLI `build_runtime` → `factory.build`.

---

## Unified command surface

| Command | SDK | CLI | MCP | Result states |
|---------|-----|-----|-----|---------------|
| `doctor` | `session.doctor()` | `broker doctor --json` | `broker_doctor` tool | `passed\|failed\|blocked` ✅ |
| `verify` | — | `broker verify [--live]` | `verify` tool | per-check matrix |
| `certify` | — | `broker certify --json` | `certify` tool | artifact path |
| `benchmark` | — | `tradex benchmark` | — | latency report |
| `diagnose` | — | `tradex diagnose` | — | structured findings |
| `replay` | `session.replay()` | `tradex replay` | — | determinism hash |

**Single core:** `brokers.platform_ops` → `brokers.services.core` → `BrokerCertifier` (per ADR-014).

| Surface | Import path | Status |
|---------|-------------|--------|
| `broker` CLI | `brokers.platform_ops` | ✅ Iteration 5 |
| MCP tools | `brokers.platform_ops` | ✅ |
| `tradex ui` broker_ops | `brokers.platform_ops` | ✅ |
| `tradex certify` | `brokers.services.run_certify` | ✅ (same `core` fn) |

Cert JSON schema v2 (`schema_version`, `tier`, `status`) validated in CI — ADR-018.

---

## Doctor matrix (target)

| Check | Owner context | Fail-closed |
|-------|---------------|-------------|
| import-linter | Operations | Yes |
| domain resolves in-repo | Operations | Yes |
| gateway bootstrap | Broker | Yes |
| event bus wired | Runtime | Yes |
| OMS context registered | OMS | Yes |
| reconciliation ready | Reconciliation | Yes (trade mode) |
| broker session authenticated | Broker | Yes |
| subscription freshness | Market Data | Yes |
| parity gate | Quant | Yes (production) |
| sqlite single-writer | Operations | Warn → Yes P7 |

Output schema (JSON):

```json
{
  "command": "doctor",
  "broker": "paper",
  "mode": "trade",
  "overall": "passed",
  "checks": [
    {"id": "oms_context", "status": "passed", "message": "..."},
    {"id": "reconciliation_ready", "status": "blocked", "message": "..."}
  ],
  "environment": {"live": false, "market_hours": false}
}
```

---

## Verify vs certify

| | verify | certify |
|---|--------|---------|
| Purpose | Pre-flight capability matrix | Release evidence artifact |
| Duration | Seconds–minutes | Minutes |
| Live | Optional tier | Tier 2+ |
| Output | Console + exit code | JSON file + checksum |
| CI | Paper blocking | Paper blocking; live nightly |

---

## Health endpoints (API — TRANS-P4-005) ✅

| Endpoint | 200 when | 503 when |
|----------|----------|----------|
| `GET /api/v1/health` | Process alive | — |
| `GET /api/v1/health/ready` | All gates passed | Any gate failed/blocked |
| `GET /api/v1/health/readyz` | Alias of `/ready` | Same |

Gates (`application.services.api_readiness`): `event_bus`, `oms_context`, `reconciliation_ready`, `broker_session`, plus datalake/view/catalog.

Matches `TradingContext` placement gate semantics.

---

## MCP parity (TRANS-P4-006)

MCP tools in `brokers.mcp.server` must call the same functions as CLI:

```
broker_doctor  → brokers.diagnostics.run_doctor
broker_verify  → BrokerCertifier.verify
broker_certify → BrokerCertifier.certify
```

Architecture tests:

- `tests/architecture/test_cert_path_unity.py` — same `run_verify`/`run_certify` fn objects
- `tests/architecture/test_platform_ops_unity.py` — CLI/MCP/UI import `platform_ops`

---

## Golden datasets (TRANS-P4-007)

Location: [`tests/fixtures/golden/manifest.yaml`](../../../tests/fixtures/golden/manifest.yaml)

| Dataset | Test consumer |
|---------|---------------|
| `upstox_bus_ticks` | `test_upstox_bus_golden.py` |
| `broker_instrument_golden` | `test_certification_paper.py` |
| `ledger_shadow_parity_24h` | `test_shadow_parity_gate.py` |

CI: `pytest tests/unit/brokers/certification -m certification` + golden arch tests.

---

## Sample applications

| App | Path | Demonstrates |
|-----|------|--------------|
| Minimal session | `examples/minimal_session/` | connect → quote → disconnect ✅ |
| Paper round-trip | `examples/paper_roundtrip/` | place → fill → position (Phase 5) |
| Replay determinism | `examples/replay_demo/` | same hash twice |

---

## Script deprecation schedule

| Script | Replacement | Deprecate after |
|--------|-------------|-----------------|
| `scripts/verify/check_dhan_connection.py` | `broker doctor --broker dhan` | P4 + 30d |
| Ad-hoc `scripts/verify/verify_*` | `broker verify` matrix | P4 + 60d |
| `production_certification.py` internals | Calls `broker certify` | P4 refactor |

Scripts remain for CI internals but **must** be referenced only via workflow-reference test.

---

## AI agent instructions (embed in Handbook)

1. Run `broker --broker paper doctor` before debugging broker code.
2. Never add `brokers.*` import to `domain/` or `application/`.
3. Pick task from `ENGINEERING-BACKLOG.md` by lane.
4. One PR per `TRANS-*` task; max ~500 LOC.
5. Update flow doc if behavior changes.
6. `lint-imports` + `tests/architecture` must pass.
7. Cite Handbook section in PR description.