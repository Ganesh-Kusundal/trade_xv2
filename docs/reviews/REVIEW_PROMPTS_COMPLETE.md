# TradeXV2 Comprehensive Code Review — Master Prompt Document

This document contains 11 complete, self-contained prompts organized into a sequential review pipeline. Each prompt is designed to be executed independently but builds on evidence from preceding stages.

---

## Review Execution Order

```
Stage 1  →  Stage 2  →  Stage 3  →  Stage 4  →  Stage 5
  ↓          ↓          ↓          ↓          ↓
Stage 6  →  Stage 7  →  Stage 8  →  Stage 9  →  Stage 10
  ↓
Stage 11 (Capstone — consumes all prior evidence)
```

---

# ╔══════════════════════════════════════════════════════════════════╗
# ║           STAGE 1 — UNDERSTAND THE FOUNDATION                   ║
# ║           "What is this system trying to be?"                   ║
# ╚══════════════════════════════════════════════════════════════════╝

## PROMPT 10 — Repository Organisation Review

### Purpose

Before reading any code, understand how the codebase is organised. Every subsequent review is faster when you know where things live, what owns what, and how dependencies flow at the folder level.

### Scope

Perform a complete repository organisation audit covering:

1. **Module Map** — Inventory every top-level and second-level directory. For each module, document:
   - What business capability it owns
   - What it depends on (imports from)
   - What depends on it (imported by)
   - Whether the directory name follows the two-word business-capability naming rule (e.g., `order-processing`, not `utils`, `helpers`, or `common`)

2. **Ownership Map** — For each module:
   - Who owns it (team, individual, or orphaned)
   - Is ownership clear from CODEOWNERS or conventions?
   - Are there modules with no clear owner?

3. **Dependency Direction Baseline** — Map import flows between modules:
   - Which modules depend on which?
   - Are there cyclic dependencies? (If module A imports B and B imports A, that's a cycle)
   - Does the dependency graph follow a clean architecture direction (inner layers don't depend on outer layers)?

4. **Duplicate Functionality Inventory** — Find functionality that exists in multiple places:
   - Same logic implemented in different modules
   - Utility functions duplicated across files
   - Similar classes with different names
   - Copy-pasted code blocks

### Non-Negotiable Rules

- **Folder structure IS architecture** — The way files are organised reveals the architectural intent
- **Module names must NEVER be** `utils`, `helpers`, `common`, `shared`, or any other vague name
- **Modules must use two-word business-capability names** (e.g., `order-processing`, `market-data`, `risk-management`)
- **Cyclic dependencies are design errors** — They indicate unclear boundaries
- **Tests must be co-located with source** — Not in a separate top-level `tests/` directory unless required by framework convention
- **Hardcoded secrets in repos are security incidents** — API keys, tokens, passwords must not exist in source code

### Severity Classification

| Severity | Label | Definition |
|----------|-------|------------|
| 🔴 | Critical | Violation that will cause production failures or security incidents |
| 🟠 | High | Violation that causes significant maintainability or scalability problems |
| 🟡 | Medium | Violation that increases complexity or slows development |
| 🟢 | Low | Violation that is cosmetic or minor inconsistency |

### Required Output Format

For each finding, use this exact format:

```
## [Finding Title]

**Location:** `[directory/file]`
**Severity:** [🔴/🟠/🟡/🟢]

**Diagnosis:**
[What is wrong and why it matters]

**Prescription:**
[How to fix it, with specific file/module references]
```

### Deliverables

1. **Current Analysis** — Complete module inventory with dependency map
2. **Dependency Graph** — Visual representation (Mermaid or ASCII) of module dependencies
3. **Duplicate Map** — Table of duplicated functionality with locations
4. **Clean Structure Design** — Proposed ideal folder structure following clean architecture
5. **Migration Plan** — Step-by-step plan to move from current to ideal structure
6. **Remediation Roadmap** — Prioritised list of fixes with effort estimates

---

# ╔══════════════════════════════════════════════════════════════════╗
# ║           STAGE 2 — REVIEW THE ARCHITECTURE                     ║
# ║           "Is the skeleton sound?"                              ║
# ╚══════════════════════════════════════════════════════════════════╝

## PROMPT 6 — System Architecture Review

### Purpose

Architecture is the frame everything else lives in. Code quality fixes inside a broken architecture are cosmetic. Understand the structural decisions before judging their execution.

### Scope

Perform a comprehensive system architecture review covering:

1. **Bounded Context Map** — Identify every bounded context in the system:
   - What business domain does each context own?
   - What are the explicit boundaries between contexts?
   - Are contexts leaking into each other (shared entities, cross-context imports)?
   - Is each context independently deployable?

2. **Dependency Rule Compliance** — Verify the dependency rule (Clean Architecture):
   - Inner layers (domain, entities) must NOT depend on outer layers (infrastructure, UI, frameworks)
   - Outer layers MAY depend on inner layers
   - Are there dependency inversions? (Inner layer defines interface, outer layer implements)
   - Are there violations where domain imports infrastructure?

3. **Domain Model Richness** — Assess the quality of the domain model:
   - Are domain entities rich with behaviour, or anemic (just data holders)?
   - Is business logic in the right place (domain layer vs. service layer)?
   - Are there primitive obsessions? (Using strings/ints instead of value objects)
   - Are domain invariants enforced by the model itself?

4. **CQRS / ES / EDA Suitability** — Assess architectural pattern fit:
   - Is Command Query Responsibility Segregation appropriate? Is it implemented correctly?
   - Is Event Sourcing used? If so, is event replay implemented correctly?
   - Is Event-Driven Architecture used? Are events properly typed and versioned?
   - Are these patterns solving real problems, or added for complexity?

5. **Scalability Ceiling** — Assess architectural limits:
   - What is the maximum throughput the architecture can support?
   - Where are the bottlenecks? (Single database, monolithic service, shared state)
   - Can the system scale horizontally? Vertically?
   - What would break first under 10x load?

6. **Architectural Bottlenecks** — Identify structural problems:
   - Single points of failure in the architecture
   - Overly coupled modules that prevent independent deployment
   - Missing abstractions that make testing difficult
   - God services that do too much

### Required Output Format

```
## [Finding Title]

**Location:** `[file/class/module#Lstart-Lend]`
**Severity:** [🔴/🟠/🟡/🟢]

**Diagnosis:**
[What architectural decision is problematic and why]

**Evidence:**
[Specific code examples, import patterns, or structural evidence]

**Prescription:**
[How to restructure, with before/after examples if helpful]
```

### Deliverables

- Complete bounded context map with boundary violations identified
- Dependency rule compliance report with violation locations
- Domain model assessment (anemic vs. rich)
- Architectural bottleneck inventory
- Scalability ceiling analysis
- Recommended architectural improvements prioritised by impact

---

# ╔══════════════════════════════════════════════════════════════════╗
# ║           STAGE 3 — REVIEW THE DOMAIN DESIGN                    ║
# ║           "Is the business logic correctly modelled?"           ║
# ╚══════════════════════════════════════════════════════════════════╝

## PROMPT 2 — Event-Driven Design Review

### Purpose

Events are the nervous system of the domain. Review event contracts, ownership, and replay before reviewing code — events reveal how the system thinks about state change.

### Scope

Perform a complete Event-Driven Architecture review covering:

1. **Event Model Integrity** — Assess event definitions:
   - Are events passed as typed objects or raw dicts/JSON? (Raw dict = 🔴 Critical)
   - Do events have clear ownership (which module publishes, which consumes)?
   - Are event schemas versioned? Is there a strategy for schema evolution?
   - Do events use past-tense naming? (e.g., `OrderPlaced`, not `PlaceOrder`)
   - Are events immutable after publication?

2. **State Corruption Risks** — Identify risks to data integrity:
   - Can events be processed out of order? What happens if they are?
   - Are there race conditions in event handlers?
   - Can partial event processing leave the system in an inconsistent state?
   - Are there transactions that span multiple event handlers?

3. **Replay Capability** — Assess event replay support:
   - Can events be replayed from a point in time?
   - Is there an event store or log?
   - Are replayed events handled idempotently?
   - What happens if replay fails midway?

4. **Idempotency Gaps** — Critical review of idempotency:
   - Any consumer lacking idempotency under at-least-once delivery = 🔴 Critical
   - Any side-effect (DB write, API call, order placement) without idempotency guard = 🔴 Critical
   - Are idempotency keys used? Where?
   - Can duplicate events cause duplicate side-effects?

5. **Missing Domain Events** — Identify gaps in event coverage:
   - Are there state changes that don't produce events?
   - Are there business operations that should emit events but don't?
   - Is event granularity appropriate (too coarse = loss of information, too fine = overhead)?

### Non-Negotiable EDA Rules

1. Any event passed as a raw dict or untyped JSON is 🔴 Critical
2. Any consumer lacking idempotency under at-least-once delivery is 🔴 Critical
3. Any side-effect without idempotency guard is 🔴 Critical
4. Passing tests do NOT prove correct ordering, replay, or idempotency — these must be verified independently

### Required Output Format

```
## [Finding Title]

**Location:** `[file/class#Lstart-Lend]`
**Event:** `[EventName or "raw dict"]`
**Severity:** [🔴/🟠/🟡/🟢]

**Diagnosis:**
[What is wrong with the event design or handling]

**Evidence:**
[Code showing the problematic pattern]

**Prescription:**
[How to fix, with typed event class example if needed]
```

### Deliverables

- Event inventory (all events, publishers, consumers)
- Idempotency gap analysis
- State corruption risk assessment
- Replay capability assessment
- Missing domain event recommendations
- Event schema versioning strategy (if missing)

---

# ╔══════════════════════════════════════════════════════════════════╗
# ║           STAGE 4 — REVIEW THE CODE                             ║
# ║           "Is the implementation honest?"                       ║
# ╚══════════════════════════════════════════════════════════════════╝

## PROMPT 1 — Static Code Analysis Review

### Purpose

Now that architecture and design are understood, review how well they are expressed in code. Code smells in the wrong layer mean more than code smells in isolation.

### Scope

Perform a deep static code analysis covering:

1. **God Class / God Service Inventory** — Identify classes/services that do too much:
   - Classes with >500 lines of code
   - Classes with >10 public methods
   - Classes with >5 dependencies
   - Classes that span multiple business concerns
   - Services that are really just procedural code

2. **SOLID Violation Map** — Assess each principle:
   - **Single Responsibility**: Does each class/module have one reason to change?
   - **Open/Closed**: Can behaviour be extended without modifying existing code?
   - **Liskov Substitution**: Can subclasses be used interchangeably with parents?
   - **Interface Segregation**: Are interfaces small and focused?
   - **Dependency Inversion**: Do high-level modules depend on abstractions, not concretions?

3. **Dead and Duplicate Code** — Find code that should be removed:
   - Unused functions, classes, variables
   - Commented-out code blocks
   - Duplicate logic (same algorithm in multiple places)
   - Feature flags for features that shipped years ago

4. **Coupling Heat Map** — Identify highly coupled code:
   - Files with >10 imports
   - Modules that import from >5 other modules
   - Circular import chains
   - Tight coupling (direct instantiation vs. dependency injection)

5. **Refactoring Prescription List** — For each finding:
   - What is the code smell?
   - What refactoring pattern applies? (Extract Method, Extract Class, Introduce Strategy, etc.)
   - What is the expected improvement?

### Required Output Format

```
## [Finding Title]

**Location:** `[file/class#Lstart-Lend]`
**Violation:** [SOLID principle / Code smell category]
**Severity:** [🔴/🟠/🟡/🟢]

**Diagnosis:**
[What the code does wrong and why it's problematic]

**Evidence:**
[Code snippet showing the violation]

**Prescription:**
[Specific refactoring to apply, with before/after code if helpful]
```

### Deliverables

- God class inventory with line counts and method counts
- SOLID violation map with severity
- Dead code inventory
- Duplicate code map
- Coupling heat map (most coupled to least)
- Prioritised refactoring prescription list

---

# ╔══════════════════════════════════════════════════════════════════╗
# ║           STAGE 5 — REVIEW THE INTEGRATIONS                     ║
# ║           "Can the system talk to the world correctly?"         ║
# ╚══════════════════════════════════════════════════════════════════╝

## PROMPT 3 — External Adapter Integration Review

### Purpose

Integrations are where architecture meets reality. Review adapter contracts, error handling, and rate limits after understanding the domain — you can now judge whether adapters correctly isolate external complexity.

### Scope

Perform a complete external adapter integration review covering:

1. **Adapter Consistency Matrix** — Assess adapter design patterns:
   - Do all adapters for similar services follow the same interface?
   - Are there port interfaces that define the contract? (Ports & Adapters pattern)
   - Do adapters translate external models to domain models, or leak external types into the domain?
   - Is there a consistent error handling pattern across adapters?

2. **Error Classification Completeness** — Assess error handling:
   - Are all error types from the external system classified? (transient, permanent, rate-limit, auth)
   - Are transient errors retried? With what strategy?
   - Are permanent errors surfaced correctly?
   - Are rate-limit errors handled with backoff?
   - Are auth errors handled with re-authentication?

3. **Rate Limit Compliance** — Assess rate limit handling:
   - Does the adapter respect the external system's rate limits?
   - Is there a rate limiter (token bucket, sliding window)?
   - Does the adapter track remaining quota?
   - What happens when rate limit is exceeded? (retry, queue, fail fast?)

4. **Reconnection Safety** — Assess WebSocket/streaming reconnection:
   - Does the adapter handle disconnections gracefully?
   - Is reconnection exponential backoff?
   - Are subscriptions re-established after reconnect?
   - Is there a maximum reconnection attempt limit?
   - What happens after max attempts? (alert, degrade, fail?)

5. **Auth Session Reliability** — Assess authentication handling:
   - How are auth tokens managed? (storage, refresh, expiry)
   - Is token refresh automatic?
   - What happens if token refresh fails?
   - Are sessions validated before use?
   - Is there a fallback if auth is unavailable?

### Required Output Format

```
## [Finding Title]

**Location:** `[file/class#Lstart-Lend]`
**Adapter:** `[AdapterName or "all adapters"]`
**Severity:** [🔴/🟠/🟡/🟢]

**Diagnosis:**
[What is wrong with the adapter integration]

**Evidence:**
[Code showing the problematic pattern]

**Prescription:**
[How to fix, with port interface or error handling pattern if needed]
```

### Deliverables

- Adapter consistency matrix (all adapters, interfaces, patterns)
- Error classification completeness report
- Rate limit compliance assessment
- Reconnection safety assessment
- Auth session reliability assessment
- Missing adapter capability recommendations

---

# ╔══════════════════════════════════════════════════════════════════╗
# ║           STAGE 6 — REVIEW THE DATA PIPELINE                    ║
# ║           "Can the system process data correctly at speed?"     ║
# ╚══════════════════════════════════════════════════════════════════╝

## PROMPT 4 — Real-Time Data Pipeline Review

### Purpose

Data quality is the foundation of correct behaviour. Review the pipeline after adapters — you now know what data enters the system and can judge how well it is processed.

### Scope

Perform a complete real-time data pipeline review covering:

1. **Tick / Event Ingestion Correctness** — Assess data ingestion:
   - Is data parsed correctly from wire format?
   - Are all fields validated before processing?
   - Is there a schema for incoming data?
   - Are malformed messages handled gracefully?
   - Is there a dead letter queue for failed messages?

2. **Deduplication and Ordering Safety** — Assess data integrity:
   - Can duplicate messages enter the pipeline?
   - Is there a deduplication mechanism? (message IDs, content hash)
   - Is message ordering preserved where required?
   - What happens if messages arrive out of order?
   - Are there sequence numbers or timestamps for ordering?

3. **Aggregation Correctness** — Assess data aggregation:
   - Are aggregations (moving averages, sums, counts) computed correctly?
   - Is there a windowing strategy? (tumbling, sliding, session)
   - Are aggregations reset correctly on window boundaries?
   - Is there a risk of overflow in aggregations?

4. **Memory Bounds** — Assess memory usage:
   - Does the pipeline bound memory usage? (no unbounded buffers)
   - Are there circular buffers or ring buffers for data?
   - What happens if the pipeline is overwhelmed? (backpressure, drop, fail?)
   - Is there a memory leak risk? (accumulating state, event listeners not removed)

5. **Concurrency Safety Map** — Assess thread/process safety:
   - Is the pipeline single-threaded or multi-threaded?
   - If multi-threaded, is there proper synchronization?
   - Are there race conditions in shared state?
   - Are data structures thread-safe?
   - Is there a risk of data corruption from concurrent access?

6. **Storage Strategy Assessment** — Assess data persistence:
   - Where is processed data stored? (memory, database, file)
   - Is storage strategy appropriate for the data volume?
   - Is there data retention policy?
   - Can historical data be replayed?
   - Is storage I/O bounded or unbounded?

### Required Output Format

```
## [Finding Title]

**Location:** `[file/class#Lstart-Lend]`
**Pipeline Stage:** `[Ingestion / Deduplication / Aggregation / Storage]`
**Severity:** [🔴/🟠/🟡/🟢]

**Diagnosis:**
[What is wrong with the pipeline stage]

**Evidence:**
[Code showing the problematic pattern]

**Prescription:**
[How to fix, with specific pattern or data structure recommendation]
```

### Deliverables

- Data ingestion correctness assessment
- Deduplication and ordering safety report
- Aggregation correctness assessment
- Memory bounds analysis
- Concurrency safety map
- Storage strategy assessment

---

# ╔══════════════════════════════════════════════════════════════════╗
# ║           STAGE 7 — REVIEW DOMAIN-SPECIFIC READINESS            ║
# ║           "Is the core business capability correctly built?"    ║
# ╚══════════════════════════════════════════════════════════════════╝

## PROMPT 7 — Quant Platform Readiness Review

### Purpose

Only after architecture, events, code, adapters, and data pipeline are understood can you judge whether the domain-specific capability (trading / quant platform) is correctly and safely implemented.

### Scope

Perform a complete quantitative trading platform readiness review covering:

1. **Strategy / Workflow Execution Model Correctness** — Assess strategy execution:
   - Are trading strategies executed correctly?
   - Is the strategy lifecycle managed? (init, run, pause, stop)
   - Are strategy parameters validated?
   - Can strategies be hot-reloaded?
   - Is there a strategy state machine?

2. **Risk Management Completeness** — Assess risk controls:
   - Is there position sizing logic?
   - Are stop-loss and take-profit implemented?
   - Is there maximum drawdown protection?
   - Are there daily loss limits?
   - Is there exposure monitoring?
   - Can risk limits be overridden? (should they?)

3. **PnL Accuracy** — Assess profit/loss calculation:
   - Is PnL calculated correctly? (realized vs. unrealized)
   - Are fees, slippage, and taxes included?
   - Is PnL updated in real-time or batch?
   - Are there rounding errors in PnL?
   - Is PnL reconciliation possible?

4. **Backtest Validity** — Assess backtesting:
   - Is the backtest engine accurate?
   - Is there look-ahead bias prevention?
   - Is there survivorship bias in the data?
   - Are transaction costs modelled correctly?
   - Can backtests be replayed deterministically?
   - Is there a paper trading mode?

5. **Execution Quality** — Assess order execution:
   - Are orders routed correctly?
   - Is there smart order routing? (best execution venue)
   - Is there order slicing for large orders?
   - Are there execution algorithms? (VWAP, TWAP, Iceberg)
   - Is there slippage monitoring?

6. **Simulation vs Live Parity** — Assess paper/live consistency:
   - Does paper trading match live trading logic?
   - Are there different code paths for paper vs. live?
   - Can a strategy switch between paper and live seamlessly?
   - Is the data source the same for paper and live?

### Required Output Format

```
## [Finding Title]

**Location:** `[file/class#Lstart-Lend]`
**Domain Area:** `[Strategy / Risk / PnL / Backtest / Execution / Parity]`
**Severity:** [🔴/🟠/🟡/🟢]

**Diagnosis:**
[What is wrong with the domain-specific implementation]

**Evidence:**
[Code showing the problematic pattern]

**Prescription:**
[How to fix, with specific trading pattern or risk control recommendation]
```

### Deliverables

- Strategy execution model assessment
- Risk management completeness report
- PnL accuracy assessment
- Backtest validity assessment
- Execution quality assessment
- Simulation vs. live parity assessment

---

# ╔══════════════════════════════════════════════════════════════════╗
# ║           STAGE 8 — REVIEW THE TESTS                            ║
# ║           "Is confidence in the system earned or assumed?"      ║
# ╚══════════════════════════════════════════════════════════════════╝

## PROMPT 5 — Testing Strategy Assessment

### Purpose

Tests must be reviewed AFTER the code and domain they test are understood. You cannot assess test coverage without knowing what should be covered. Test quality must be judged against what the system actually does, not in isolation.

### Scope

Perform a complete testing strategy assessment covering:

1. **Test Pyramid Shape** — Assess test distribution:
   - What is the ratio of unit tests to integration tests to end-to-end tests?
   - Is the pyramid inverted? (too many E2E, too few unit tests)
   - Are tests at the right level of the pyramid?
   - Is there a contract test layer?

2. **Coverage Gap Map** — Assess test coverage:
   - What code is not covered by tests?
   - Are critical paths covered? (order lifecycle, risk checks, PnL calculation)
   - Are edge cases tested? (empty data, network failures, rate limits)
   - Are error paths tested?
   - Is coverage measured and enforced in CI?

3. **Chaos Test Inventory** — Assess failure testing:
   - Are there tests for network failures?
   - Are there tests for broker disconnections?
   - Are there tests for data corruption?
   - Are there tests for concurrent access?
   - Is there fault injection?

4. **Missing Test Catalogue** — Identify missing tests:
   - What functionality has no tests?
   - What edge cases are not tested?
   - What integration points are not tested?
   - What failure scenarios are not tested?

5. **CI Pipeline Health** — Assess CI/CD:
   - Does CI run all tests?
   - Is there a test timeout?
   - Are tests flaky?
   - Is there a coverage threshold in CI?
   - Are tests parallelised?
   - Is there a pre-commit hook for tests/linting?

### Required Output Format

```
## [Finding Title]

**Location:** `[file/test_class#Lstart-Lend]`
**Test Type:** `[Unit / Integration / E2E / Chaos / Missing]`
**Severity:** [🔴/🟠/🟡/🟢]

**Diagnosis:**
[What is wrong with the testing strategy]

**Evidence:**
[Code showing the gap or problematic pattern]

**Prescription:**
[How to fix, with test pattern or CI configuration recommendation]
```

### Deliverables

- Test pyramid assessment
- Coverage gap map (prioritised by risk)
- Chaos test inventory
- Missing test catalogue
- CI pipeline health assessment

---

# ╔══════════════════════════════════════════════════════════════════╗
# ║           STAGE 9 — REVIEW PERFORMANCE                          ║
# ║           "Can the system sustain real load?"                   ║
# ╚══════════════════════════════════════════════════════════════════╝

## PROMPT 9 — Performance Review

### Purpose

Performance must be assessed after understanding architecture, data pipeline, and domain logic — only then can you distinguish design-level performance problems (architecture) from implementation-level ones (code).

### Scope

Perform a complete performance review covering:

1. **Latency Budget and Gaps** — Assess latency:
   - What is the end-to-end latency from market data to order execution?
   - Where are the latency bottlenecks?
   - Is latency measured and monitored?
   - Is there a latency budget per component?
   - Are there latency SLOs?

2. **Throughput Ceiling Model** — Assess throughput:
   - What is the maximum messages/second the system can process?
   - What is the maximum orders/second the system can execute?
   - Where does throughput bottleneck? (CPU, I/O, network, database)
   - Can throughput scale horizontally?

3. **Memory Growth Projection** — Assess memory usage:
   - Does memory usage grow over time? (leak)
   - What is the memory footprint per connection/stream?
   - Is there a maximum memory limit?
   - What happens if memory is exhausted?

4. **CPU Hot Path Profile** — Assess CPU usage:
   - What are the CPU-intensive operations?
   - Are there unnecessary computations?
   - Are there inefficient algorithms? (O(n²) where O(n) is possible)
   - Is CPU usage monitored?

5. **Capacity Plan** — Assess scaling:
   - What is the current capacity utilisation?
   - When will capacity be exhausted?
   - What is the scaling strategy? (vertical, horizontal)
   - Is there a load testing regime?

### Required Output Format

```
## [Finding Title]

**Location:** `[file/function#Lstart-Lend]`
**Metric:** `[Latency / Throughput / Memory / CPU]`
**Severity:** [🔴/🟠/🟡/🟢]

**Diagnosis:**
[What is the performance problem]

**Evidence:**
[Code showing the problematic pattern or benchmark results]

**Prescription:**
[How to fix, with specific optimisation or architectural change]
```

### Deliverables

- Latency budget and gap analysis
- Throughput ceiling model
- Memory growth projection
- CPU hot path profile
- Capacity plan

---

# ╔══════════════════════════════════════════════════════════════════╗
# ║           STAGE 10 — REVIEW RELIABILITY & OPERATIONS            ║
# ║           "Will the system survive the real world?"             ║
# ╚══════════════════════════════════════════════════════════════════╝

## PROMPT 8 — Reliability & Operational Readiness Review

### Purpose

Reliability is the synthesis layer. It can only be assessed after architecture, integrations, data pipeline, domain logic, testing, and performance are all understood. A reliability review without that context produces a checklist. With that context it produces a risk model.

### Scope

Perform a complete reliability and operational readiness review covering 9 phases:

1. **Single Points of Failure (SPOF)** — Identify SPOFs:
   - What components have no redundancy?
   - What happens if each SPOF fails?
   - What is the blast radius of each SPOF?
   - Can the system degrade gracefully?

2. **Failover Mechanisms** — Assess failover:
   - Is there automatic failover for critical components?
   - How long does failover take?
   - Is there data loss during failover?
   - Is failover tested?

3. **Retry Strategies** — Assess retry logic:
   - What operations are retried?
   - Is retry exponential backoff?
   - Is there a maximum retry limit?
   - Is there jitter to prevent thundering herd?
   - Are retries idempotent?

4. **Circuit Breakers** — Assess circuit breaker patterns:
   - Are there circuit breakers for external dependencies?
   - What are the failure thresholds?
   - Is there a half-open state for testing recovery?
   - Is circuit breaker state monitored?

5. **Dead Letter Queues** — Assess failed message handling:
   - Are failed messages sent to a dead letter queue?
   - Can dead letter messages be reprocessed?
   - Is there alerting on dead letter queue growth?
   - Is there a maximum retry count before dead letter?

6. **Health Checks** — Assess health monitoring:
   - Are there liveness probes? (is the process alive?)
   - Are there readiness probes? (is the service ready to accept traffic?)
   - Are there custom health checks? (database connectivity, broker connectivity)
   - Is health check endpoint exposed?

7. **Monitoring** — Assess observability:
   - Are the Four Golden Signals monitored? (latency, traffic, errors, saturation)
   - Are business metrics monitored? (orders placed, PnL, positions)
   - Are there dashboards?
   - Is there distributed tracing?
   - Are logs structured and queryable?

8. **Alerting** — Assess alert coverage:
   - Are alerts symptom-based? (high latency, errors) not cause-based (CPU high)
   - Are alerts actionable? (can the on-call engineer do something?)
   - Is there alert fatigue? (too many alerts, ignored alerts)
   - Are there escalation policies?

9. **Recovery Procedures** — Assess runbooks:
   - Are there runbooks for common failures?
   - Can the system be recovered from backup?
   - What is the RTO (Recovery Time Objective)?
   - What is the RPO (Recovery Point Objective)?
   - Are runbooks tested?

### Required Output Format

```
## [Finding Title]

**Location:** `[file/class#Lstart-Lend]`
**Phase:** `[SPOF / Failover / Retry / Circuit Breaker / DLQ / Health / Monitoring / Alerting / Recovery]`
**Severity:** [🔴/🟠/🟡/🟢]

**Diagnosis:**
[What is the reliability gap]

**Evidence:**
[Code showing the missing pattern or problematic design]

**Prescription:**
[How to fix, with specific reliability pattern recommendation]
```

### Deliverables

- SPOF map with blast radius
- Failure mode register
- Retry strategy assessment
- Circuit breaker assessment
- Dead letter queue assessment
- Health check assessment
- Monitoring coverage matrix (Four Golden Signals + business metrics)
- Alert coverage matrix
- Runbook inventory
- RTO / RPO baseline

---

# ╔══════════════════════════════════════════════════════════════════╗
# ║           STAGE 11 — RENDER THE VERDICT                         ║
# ║           "Is this system ready for production?"                ║
# ╚══════════════════════════════════════════════════════════════════╝

## PROMPT 11 — Production Readiness Assessment

### Purpose

This is the capstone. It consumes evidence from all ten preceding reviews and converts them into scores, risks, and a prioritised roadmap. Running this first produces opinions. Running it last produces verdicts.

### Prerequisites

This assessment MUST be performed AFTER completing Stages 1-10. It consumes evidence from:
- Stage 1: Repository Organisation Review
- Stage 2: System Architecture Review
- Stage 3: Event-Driven Design Review
- Stage 4: Static Code Analysis Review
- Stage 5: Testing Strategy Assessment
- Stage 6: Real-Time Data Pipeline Review
- Stage 7: Quant Platform Readiness Review
- Stage 8: Reliability & Operational Readiness Review
- Stage 9: Performance Review
- Stage 10: External Adapter Integration Review

### Scope

Perform a complete production readiness assessment covering 10 dimensions:

1. **Architecture** (weight: 15%)
   - Is the architecture sound?
   - Are bounded contexts clear?
   - Is the dependency rule followed?
   - Are there architectural bottlenecks?

2. **Domain Design** (weight: 10%)
   - Is the domain model rich?
   - Are events properly designed?
   - Is idempotency guaranteed?

3. **Code Quality** (weight: 10%)
   - Are SOLID principles followed?
   - Are there god classes?
   - Is there dead/duplicate code?

4. **Integration Quality** (weight: 10%)
   - Are adapters consistent?
   - Is error handling complete?
   - Are rate limits respected?

5. **Data Pipeline Quality** (weight: 10%)
   - Is ingestion correct?
   - Is deduplication safe?
   - Is memory bounded?

6. **Domain-Specific Readiness** (weight: 15%)
   - Is strategy execution correct?
   - Is risk management complete?
   - Is PnL accurate?

7. **Testing Quality** (weight: 10%)
   - Is the test pyramid healthy?
   - Are critical paths covered?
   - Are there chaos tests?

8. **Performance** (weight: 5%)
   - Is latency within budget?
   - Is throughput sufficient?
   - Is memory bounded?

9. **Reliability** (weight: 10%)
   - Are there SPOFs?
   - Is there failover?
   - Is monitoring complete?

10. **Operations** (weight: 5%)
    - Are there runbooks?
    - Is alerting actionable?
    - Is recovery tested?

### Scoring Rules

- Each dimension is scored 1-10
- Every score MUST be justified with 3+ specific findings from prior stages
- Scores are weighted and combined for overall readiness score
- "Almost ready" is NOT a valid verdict — either it's ready or it's not
- Protecting users, data, and business takes priority over team encouragement

### Required Output Format

```
# Production Readiness Assessment

## Executive Summary

[2-3 sentence verdict: Is this system production-ready? Why or why not?]

## Scorecard

| Dimension | Weight | Score | Key Findings |
|-----------|--------|-------|--------------|
| Architecture | 15% | X/10 | [3 key findings] |
| Domain Design | 10% | X/10 | [3 key findings] |
| Code Quality | 10% | X/10 | [3 key findings] |
| Integration Quality | 10% | X/10 | [3 key findings] |
| Data Pipeline Quality | 10% | X/10 | [3 key findings] |
| Domain-Specific Readiness | 15% | X/10 | [3 key findings] |
| Testing Quality | 10% | X/10 | [3 key findings] |
| Performance | 5% | X/10 | [3 key findings] |
| Reliability | 10% | X/10 | [3 key findings] |
| Operations | 5% | X/10 | [3 key findings] |
| **Weighted Total** | **100%** | **X/10** | |

## Top 20 Risks (Evidence-Backed)

1. [Risk description] — Evidence: [finding from Stage X]
2. ...
20. ...

## Top 20 Improvements (Impact-Ordered)

1. [Improvement] — Impact: [High/Medium/Low] — Effort: [Days]
2. ...
20. ...

## Quick Wins (1-2 Days)

- [Quick win 1]
- [Quick win 2]
- ...

## Medium-Term Plan (1-4 Weeks)

- [Initiative 1]
- [Initiative 2]
- ...

## Long-Term Strategic Roadmap (1-6 Months)

- [Strategic initiative 1]
- [Strategic initiative 2]
- ...

## Verdict

[Clear, honest verdict: PRODUCTION READY / NOT PRODUCTION READY with justification]
```

### Deliverables

- Weighted scorecard across 10 dimensions
- Top 20 risks (evidence-backed from prior stages)
- Top 20 improvements (impact-ordered)
- Quick wins (1-2 days each)
- Medium-term plan (1-4 weeks)
- Long-term strategic roadmap (1-6 months)
- Production readiness verdict

---

# APPENDIX A — Severity Classification Reference

| Severity | Label | When to Use |
|----------|-------|-------------|
| 🔴 | Critical | Will cause production failure, security incident, data corruption, or financial loss |
| 🟠 | High | Will cause significant maintainability, scalability, or reliability problems |
| 🟡 | Medium | Increases complexity, slows development, or creates future risk |
| 🟢 | Low | Cosmetic, minor inconsistency, or best practice violation with no immediate impact |

---

# APPENDIX B — Output Consistency Rules

1. **Every finding must have a code location** — `[file/class#Lstart-Lend]` format
2. **Every finding must have a severity** — 🔴/🟠/🟡/🟢
3. **Every finding must have a diagnosis** — What is wrong and why it matters
4. **Every finding must have a prescription** — How to fix it
5. **Every score must be justified** — 3+ specific findings from prior stages
6. **No vague claims** — "could be improved" is not a finding
7. **No encouragement rounding** — 6.5 stays 6.5, not "almost 7"
8. **Evidence must be traceable** — Every risk/improvement must reference a finding from Stages 1-10

---

# APPENDIX C — Review Execution Checklist

- [ ] Stage 1: Repository Organisation Review — Module map, ownership, dependency direction, duplicates
- [ ] Stage 2: System Architecture Review — Bounded contexts, dependency rule, domain model, scalability
- [ ] Stage 3: Event-Driven Design Review — Event contracts, idempotency, replay, state corruption
- [ ] Stage 4: Static Code Analysis Review — God classes, SOLID violations, dead code, coupling
- [ ] Stage 5: External Adapter Integration Review — Adapter consistency, error handling, rate limits, reconnection
- [ ] Stage 6: Real-Time Data Pipeline Review — Ingestion, deduplication, aggregation, memory, concurrency
- [ ] Stage 7: Quant Platform Readiness Review — Strategy execution, risk management, PnL, backtest, parity
- [ ] Stage 8: Testing Strategy Assessment — Test pyramid, coverage gaps, chaos tests, CI health
- [ ] Stage 9: Performance Review — Latency, throughput, memory, CPU, capacity
- [ ] Stage 10: Reliability & Operational Readiness — SPOFs, failover, retry, circuit breakers, monitoring, alerting, recovery
- [ ] Stage 11: Production Readiness Assessment — Scorecard, risks, improvements, roadmap, verdict

---

# APPENDIX D — TradeXV2 Context

This review pipeline is designed for **TradeXV2**, a quantitative trading platform with:

- **Broker integrations**: Dhan, Upstox, Paper trading
- **Domain**: Order management, strategy execution, risk management, PnL calculation
- **Architecture**: Event-driven, ports/adapters pattern
- **Data pipeline**: Real-time WebSocket market data, historical data loading
- **CLI**: Command-line trading interface
- **API**: FastAPI-based REST API
- **Frontend**: React/Vite-based web UI

Review each stage with this context in mind. Trading systems have zero tolerance for:
- PnL calculation errors
- Order execution failures
- Risk management gaps
- Data integrity issues
- Race conditions in position tracking
