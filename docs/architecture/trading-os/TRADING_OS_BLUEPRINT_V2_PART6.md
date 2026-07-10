# Trading OS — Blueprint v2, Part 6: Cross-Cutting Concerns (Closing Part)

**Continues from and closes:** Parts 1–5. Covers observability, security,
config, concurrency, testing strategy, migration roadmap, and quality
gates — then a dedicated ADR audit, because auditing this repository's
*own existing seven ADRs* against verified reality turned up the single
largest finding in this entire blueprint.

---

## 1. Observability, Security, Config — real, cited briefly (no redesign)

| Concern | Real components (verified) | Verdict |
|---|---|---|
| **Observability** | `infrastructure/observability/{audit.py, alerting.py, health_check.py, http_server.py}` | Real, already covered in Part 3 §2.1 (the `infrastructure.observability.audit` module distinct from `application.audit`). No new design needed. |
| **Security** | `infrastructure/security/{secret_manager.py, ssl_hardening.py}`; `SecretManager.get_instance()` already used correctly by `brokers/upstox/auth/encrypted_token_state_store.py` (Fernet-encrypted token persistence, verified earlier this session) | Real and reasonably designed. Deferred formally, and correctly so — `docs/architecture/TARGET_SYSTEM_DESIGN.md` §12 already states multi-tenant auth, secret vaults, and MFA are explicitly out of scope for the current single-operator deployment model this blueprint (Part 1 §1) also assumes. Re-deciding that here would contradict Part 1's own mandate ("Never optimize prematurely.") applied to security scope, not just code. |
| **Config** | `config/{validator.py, secrets_manager.py, feature_flags.py, indices.py, defaults.py, endpoints.py, schema.py}` | Real, schema-validated, feature-flagged. No redesign proposed. |

---

## 2. Concurrency model — real, mostly disciplined, one confirmed counter-example

Every hot state owner already uses explicit, scoped locking:
`OrderManager` (shared `RLock` across order/position mutation),
`Instrument._lock` (`threading.RLock`, Part 2 §1), `PositionManager`,
`TradeRecorder`. This is the right default for a modular monolith (Part 1
§2's "explicit owners + locks/queues at hot boundaries" over an actor
model) — not proposing anything different.

**The counter-example, already found and already fixed once this
session, restated here because Part 6 is where a concurrency *policy*
belongs, not just a bug list:** `brokers/dhan/execution/
order_placement.py`'s `IdempotencyCache.get()` read `self._cache` without
holding its lock, then deleted an expired entry under a *different* lock —
a genuine, confirmed race (`KeyError` under concurrent expiry). The lesson
this blueprint draws from it as policy, not just as a fixed bug: **every
mutable state owner in this codebase must document its lock's exact scope
in one place (a docstring or a `# Lock order:` comment, the pattern
already used correctly in the *same file*'s `IdempotencyCache` class
docstring — "Lock order: `_lock` is always acquired before
`_pending_lock`" — the documentation existed right next to the bug it
didn't prevent).** A stated lock-order convention is necessary but not
sufficient; §3.3's Part 4 recommendation (consolidate the two broker-level
idempotency caches into one, shared, correctly-tested component) is the
concrete fix. This section's job is naming the general policy the fix is
an instance of: **read paths that later take a lock to mutate must take
that same lock before reading, not after** — worth a lint rule or a code
review checklist line item, not just a one-off patch.

---

## 3. Testing strategy — already comprehensive, cited not redesigned

`pyproject.toml`'s marker set (verified: `unit`, `contract`, `dhan`,
`integration`, `sandbox`, `live_readonly`, `performance`, `upstox`,
`upstox_integration`, `upstox_sandbox`, `upstox_live_readonly`,
`upstox_sdk_compat`, `stress`, `pre_prod`, `regression`,
`off_market_safe`, `market_hours`, `auth_integration`, `cli_endpoint`,
`cli_endpoint_live`, `cli_endpoint_sandbox`, `paper_replay_parity`,
`cross_broker_parity`, `live_backtest_parity`, `scanner_determinism`,
`feature_parity`, `oms_integration`, `memory`, `e2e`, `slow`,
`live_orders`, `property`, `component`, `mutation`) already implements a
full pyramid **exceeding** what `docs/adr/ADR-007-test-pyramid-live-gating.md`
originally specified — ADR-007 lists roughly a dozen markers; the live
`pyproject.toml` has thirty-plus. The test pyramid grew correctly over
time; ADR-007 itself is stale on specifics (see §4) even though its
*policy* (live gating via `TRADEX_LIVE_TESTS`/`TRADEX_LIVE_ORDERS`,
never-in-CI real order placement) is still exactly right and still
followed. Nothing to redesign; ADR-007 needs a refresh, not a reversal.

---

## 4. ADR audit — the largest single finding in this blueprint

Seven ADRs exist (`docs/adr/ADR-001` through `ADR-007`), all marked
**"Status: Accepted (Phase 0)."** Each was checked against verified reality
from Parts 1–5, not taken on the label's word.

| ADR | Decision | Verified reality | Recommended status |
|---|---|---|---|
| **001** src-layout | Target tree uses `src/plugins/<broker>/`, `src/api/`, `src/ui/` | Actual tree uses `src/brokers/<broker>/`, `src/interface/api/`, `src/interface/ui/` — different names, same intent | **Accepted, superseded on naming** — the src-layout decision itself holds; the specific target paths in the ADR text don't match and should be corrected, not re-litigated |
| **002** domain ports as only broker contract | "No code outside `src/plugins` and `src/infrastructure` may import `brokers.*`" | The *constraint* is real and enforced today via import-linter contracts (Part 1 §5.2, directly verified) — but the path (`src/plugins`) never existed; the actual enforcement point is `brokers.common.*` and the composition root | **Accepted, superseded on naming** — same pattern as 001 |
| **003** capability model | "`domain/extensions/*` is moved + renamed to `domain/capabilities/*`"; typed API `instrument.capabilities.depth(levels=200)` | **Did not happen.** Both directories exist today, serving *different* purposes: `domain/extensions/` (10 files — `facade.py`, `broker_bundle.py`, `super_order.py`, `forever_order.py`, `news.py`, etc.) is the real, actively-developed broker-extension system Part 2 verified as `instrument.broker.depth20()`. `domain/capabilities/` (3 files) is a *separate* concept — the `BrokerCapabilities`/rate-limit/historical-window model Part 4 verified. The typed `instrument.capabilities.depth(levels=200)` API this ADR specifies was never built; the real API is `instrument.broker.depth20()` / `instrument.get_extension(name)` | **Superseded — recommend marking explicitly**, not left "Accepted" while contradicting the current, working code. The current `domain/extensions` + `domain/capabilities` split is not wrong, just different from what ADR-003 planned; a new ADR should describe what actually exists, or the two directories' distinct purposes should be renamed to stop implying the merge ADR-003 promised is still pending |
| **004** event-driven domain | Prescribes event classes `QuoteChanged`, `TickReceived`, `OrderPlaced`, `OrderFilled`, `MarketOpened`, `MarketClosed`, `ReplayStarted`, `ReplayFinished`, etc. | **Zero of these names exist** in the real `EventType` enum (Part 3 §2, 50+ verified members: `TICK`, `QUOTE`, `ORDER_PLACED`, `TRADE_FILLED`, `POSITION_OPENED`/`CLOSED`, no `MarketOpened`/`ReplayStarted` in any form) | **Superseded** — the *policy* (event-driven collaboration, immutable payloads) is correct and followed (Part 3 confirmed frozen `TypedDomainEvent` subclasses for newer events); the *specific catalog* in the ADR text is fiction relative to the real enum and should be replaced with a reference to `domain/events/types.py` as the living source of truth, not a static list in a document that will drift again |
| **005** brokers as plugins, domain never imports infra | Import-linter contracts named specifically | **Directly verified as real and currently enforced** (Part 1 §5.2 quotes the actual `pyproject.toml` contracts) | **Accepted, confirmed still true** — the one ADR of the seven that fully matches current reality on both policy and mechanism |
| **006** deletion strategy — no compat/shim/transitional layers, no `DeprecationWarning` wrappers | "Each phase deletes its old counterpart in the same PR... no `DeprecationWarning` wrappers" | **Comprehensively not followed.** Verified count: **58 files** across `src/` contain `"Backward-compat"`, `"Compat shim"`, or `DeprecationWarning` — including the entire `tradex.runtime` facade package (a deliberate, actively-maintained ~90-entry compatibility mapping with its own dedicated test file verifying the deprecation warnings fire correctly), the `domain.aggregates.instrument.InstrumentAggregate` alias (still emitting a live `DeprecationWarning` in every test run this session observed), and multiple `brokers/dhan/*.py` files whose entire content is a one-line `"""Backward-compat shim"""` docstring plus a re-export | **Superseded — the most significant correction in this audit.** This is not a subtle drift; it is the opposite policy, adopted deliberately and extensively. Recommend: mark ADR-006 formally Superseded by a new ADR documenting the *actual* policy in effect — "shims are permitted for gradual migration, must emit `DeprecationWarning`, and must have a tracked removal path" — because that is what the codebase actually does, consistently and on purpose, and pretending otherwise via a stale "Accepted" label makes ADR-006 actively misleading to a new engineer (or AI agent) who reads it and reasonably assumes shims are forbidden |
| **007** test pyramid & live gating | Marker list from Phase 0 | **Policy correct and followed; marker list stale** — real `pyproject.toml` has 3x the markers listed (§3) | **Accepted, needs a refresh** — update the table, keep the ADR |

**Why this matters more than a documentation-hygiene note:** Part 1's
mandate opened by saying the test for every decision in this document is
whether an engineer or an AI agent three years from now makes fewer
mistakes because it exists. An ADR marked "Accepted" that the actual
codebase has visibly and deliberately reversed (ADR-006) makes that
*worse*, not better — it's a trap, not neutral dead weight. **Recommended
action, concrete and small:** update the `Status` line on ADR-003, 004,
and 006 to `Superseded (see docs/architecture/trading-os/ — 2026-07-10
audit)` with a one-line pointer to this section, rather than deleting them
(deleting would lose the historical context of what was originally
intended and why it changed) or silently leaving them as-is (misleading).
This is a five-line edit per file, not a rewrite.

---

## 5. Migration roadmap — deliberately not re-derived

`docs/architecture/TARGET_SYSTEM_DESIGN.md`'s Phase 0–4 commit plan is
real, detailed, and already correctly sequenced (Phase 0: money-path
truth → Phase 1: one order path → Phase 2: platform depth → Phase 3: quant
depth → Phase 4: scale-only-if-needed). Re-deriving a competing roadmap
here would repeat the exact mistake this blueprint has avoided everywhere
else: producing a second version of something already good. Instead, here
is what Parts 1–5's verification work resolves about that existing plan's
status, cross-referenced by its own commit IDs:

| Existing plan item | Status per this blueprint's verification |
|---|---|
| C0.7a "Dhan `get_order` on gateway" | **Done** — confirmed via `DhanBrokerGateway.get_order` delegating correctly (verified this session) |
| C0.7b "Upstox subscribe kwargs" | **Done** — confirmed via `UpstoxDataProvider.subscribe` mode-mapping fix (verified this session) |
| C1.2 "Extended orders full risk" | **Done** — confirmed via `extended_order_service.py::_check_risk`, six of seven methods wired (Part 5 §3) — the plan's own "(R7)" comment in the code confirms this was the fix for exactly this planned item |
| C1.1 "canonical OrderService/PlaceOrderUseCase, then rewire clients" | **Half done** — the canonical class exists (`PlaceOrderUseCase`) but has zero callers (Part 5 §2.1); the "rewire clients" half of this commit item is the real remaining work, now scoped precisely instead of vaguely |
| C2.12 "tradex.runtime non-shim shrink" | **Not started, and ADR-006's status (§4) explains why it hasn't felt urgent** — as long as shims are the de facto accepted policy rather than a tracked exception, there's no forcing function driving this item forward |

This is the actual value Part 6 adds to the migration story: not a new
plan, but a verified status update on the existing one, plus the one
structural reason (ADR-006's silent reversal) that explains why one
specific item (C2.12) has stalled.

---

## 6. Quality gates — real, one already-identified gap, no new gate invented

Import-linter contracts (Part 1 §5.2) and the CI test-pyramid markers
(§3) are the real, currently-enforced quality gates. The one confirmed
gap needing a new gate is already named precisely in Part 4 §3.1: capability
mismatches are logged, not enforced. **The concrete gate to add:** a boot-time
assertion (not a new test file — an actual startup check) that
`validate_gateway_capabilities()`'s return value, if non-empty, either
aborts composition-root startup or strips the mismatched capability flags
before they're advertised — turning today's silent warning into the
fail-closed behavior Part 1 §1 and the existing `TARGET_SYSTEM_DESIGN.md`
§6 startup invariants both already require.

---

## 7. Definition of Done for this blueprint

Per Part 1 §1's mandate — does this reduce mistakes three years out, not
does it look complete — the concrete, checkable exit criteria for treating
Parts 1–6 as adopted:

1. Import-linter contracts extended to cover the Risk/Trading and
   Strategy/Analytics context splits named in Part 1 §5 (currently
   partially covered — Trading/Risk are not yet separately enforced).
2. `RiskProfile` (Part 2 §3.1) and `SignalDTO.to_intent()` (Part 2 §3.3)
   shipped and exercised by at least one real caller.
3. The `exit_all`/kill-switch policy question (Part 5 §3.1) resolved
   explicitly, either direction, and documented — not left implicit.
4. `PlaceOrderUseCase` either adopted by all three call sites or deleted
   if a decision is made not to pursue the consolidation (Part 5 §2.1) —
   either outcome is acceptable; leaving it unused indefinitely is not.
5. The two broker-level idempotency caches consolidated (Part 4 §3.3).
6. ADR-003, 004, and 006 status lines corrected (§4).
7. AI Agent tool surface (Part 5 §7) has a first real implementation,
   even a minimal one — the mandate lists it as required, and today it is
   the one capability with zero code behind it.

Everything else audited across all six parts — the Order state machine,
apply-then-mark, the broker contract test suite, the capability model, the
rate-limiter reuse pattern, the domain object hierarchy, the dependency
graph — was found correct and is not on this list because it does not need
to change.

---

*End of Trading OS Blueprint v2. Six parts, cross-referenced throughout,
each verified against source before being written down. Supersedes
`TRADING_OS_BLUEPRINT.md` pending your review and approval, per the
decision recorded at the top of Part 1.*
