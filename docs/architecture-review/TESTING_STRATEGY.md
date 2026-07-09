# Testing Strategy — TradingOS

**Deliverable 12** (per Charter Phase 10). Status: DESIGN ONLY.

## 1. Principle
Follow the **Test Pyramid**. **Mock only external boundaries** (broker network, market feed,
storage IO, system clock). Everything internal (domain, runtimes, OMS, scanners) is tested with
real collaborators or fakes — never mocked away. Reuse the existing 597 test files; do not
discard working tests during evolution.

## 2. Test levels
| Level | Scope | Existing anchor | Notes |
|---|---|---|---|
| Unit | domain objects, VOs, pure functions | `src/domain/tests/*` | Rich-domain behavior (buy/sell, state machines). |
| Domain | aggregates + invariants | `test_instrument`, `test_portfolio`, `test_invariants` | One-source-of-truth enforcement. |
| Integration | runtime wiring, ports→adapters | `tests/integration/*` | RuntimeContext mounts runtimes. |
| Broker contract | adapter vs port contract | `BrokerContractSuite`, `*GatewayContract` | Dhan/Upstox/Paper must satisfy same contract. |
| Replay | replay == live event stream | `verify_event_replay.py` → suite | Fidelity gate (Data Lake §5). |
| Data lake validation | schema/partition/ID mapping | `datalake/validation` | On write + CI. |
| Performance | latency/throughput | `.benchmarks/*`, `benchmarks` | EventBus, DuckDB query, replay speed. |
| Regression | characterization | `test_parity_characterization`, `parity_gate` | Protect behavior during refactor. |
| Property-based | invariants under many inputs | `hypothesis` (`.hypothesis/` present) | Order state machine, normalization, IDs. |
| E2E trading | full Signal→PnL scenario | `test_trading_orchestrator_e2e` | Live + paper + replay variants. |

## 3. Architecture tests (guardrails)
- `tests/test_architecture.py` (AST fitness) — must be green; currently **red on D1**.
- `lint-imports` (import-linter) — enable in-function import analysis so hidden violations
  surface; target **zero `ignore_imports`** by Phase G.
- These run in CI as a gate; a red guardrail blocks merge (Charter Loop step 8).

## 4. Mocking policy
- Allowed: broker HTTP/WS, exchange feed, filesystem/DB IO, wall clock.
- Forbidden: mocking domain objects, OMS internals, EventBus, runtimes. Use in-memory fakes
  (`src/domain/tests/_fakes.py`) instead.

## 5. Coverage & gates
- Domain: high coverage (invariants are safety-critical).
- Architecture fitness + contract tests are **mandatory merge gates**.
- Performance benchmarks run on touched paths; regression > X% fails CI.
- Each Phase A–G has an explicit Validation Checklist (`TARGET_ARCHITECTURE.md` §14).

## 6. Evolution guidance
- Add tests *before* refactoring legacy modules (Feathers: characterize first).
- Keep broker contract tests broker-agnostic; a new broker must pass them unmodified.
