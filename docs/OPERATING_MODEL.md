# TradeX Operating Model

**Status:** Canonical — engineering constitution  
**Effective:** 2026-07-09  
**Authority:** Single source of truth for how we plan, build, review, and ship.  
**Supersedes for execution priority:** architecture redesign roadmaps, pure-refactor waves, and package-centric programs when they conflict with this document.

Living work queue: [`reports/ENGINEERING_BACKLOG.md`](../reports/ENGINEERING_BACKLOG.md)  
Epic plans: `reports/EPIC_*_PLAN.md`

---

## 1. Vision

Build a **pluggable Trading Operating System** for Indian markets:

- Object-centric product API (`tradex.connect` → `Session` → `Instrument`)
- Brokers, storage, and transport stay behind ports
- Live / paper / research share the same domain model
- Production-safe by default (fail closed on money paths)

We are not building “perfect architecture.” We are building a **deployable Trading OS that improves continuously**.

---

## 2. Mission

> **Build a Trading Operating System that delivers production-ready features continuously while improving the architecture through small, incremental, measurable changes.**

Every decision — backlog item, PR, refactor, design doc — is judged against that sentence.

---

## 3. Engineering principles

Drawn from Clean Architecture / SOLID (Martin), pragmatic OO (Subramaniam), evolutionary design (Fowler), and DDD (Evans), applied to a quant trading platform.

| Principle | In practice |
|-----------|-------------|
| **Domain first** | Money, orders, instruments, and risk live in domain language — not REST shapes or gateway methods. |
| **Dependency rule** | Dependencies point inward. Domain never imports brokers, infra, API, or CLI. |
| **Ports & adapters** | Application and domain depend on protocols; adapters implement them at the edge. |
| **Tell, don’t ask** | Prefer `instrument.buy(...)` / `instrument.refresh()` over orchestrating managers in user code. |
| **One state owner** | One concept → one authoritative owner (order lifecycle, quote state, subscription). |
| **Fail closed on live** | Unknown status, missing margin, missing OMS, weak auth → refuse the unsafe path. |
| **Evolutionary architecture** | Fitness functions and small steps beat multi-month freezes. |
| **YAGNI with judgment** | No speculative frameworks. Build the next capability; leave seams only where pain is real. |
| **Measurable change** | Prefer refactors with a user story, a failing test, or a boundary violation as the driver. |

### Priority order (when goals conflict)

```text
Correctness
  → Reliability
    → Developer experience
      → Performance
        → Architecture clarity
          → Micro-optimization
```

Architecture is never ignored — it is **not allowed to outrank correctness, reliability, or shipping a working capability**.

---

## 4. Value-first development philosophy

We organize work around **business capabilities**, not packages.

| Epic | Capability |
|------|------------|
| Epic 1 | Market Access |
| Epic 2 | Trading |
| Epic 3 | Derivatives |
| Epic 4 | Analytics |
| Epic 5 | Automation |
| Epic 6 | AI |

Each epic is independently releasable. Infrastructure work exists only when it **enables** a capability, **protects money**, or **unblocks maintainability of code we are already changing**.

### Delivery shape of every work item

```text
Feature
  → Engineering improvements required (only those that enable the feature)
    → Tests
      → Documentation
        → Release
```

### Forbidden shape

```text
Refactor → Refactor → Refactor → maybe Feature
```

There is **no standalone refactoring epic**. Category C improvements ride along with feature work (Boy Scout Rule).

---

## 5. What is frozen (change rarely)

These are foundation. Change only with explicit design review, tests, and migration notes.

| Surface | Freeze rule |
|---------|-------------|
| **Domain model** | Aggregates and value objects (`Order`, `Trade`, `Position`, `Instrument`, `Money`, `Quantity`, core events). Additive evolution preferred; no silent semantic changes. |
| **Public SDK** | `tradex.connect`, `Session`, `Universe`, instrument behaviors used in docs/examples. Breaking changes require version note + migration path. |
| **Event contracts** | Event type names and payload schemas. Version or dual-publish; do not mutate in place. |
| **Broker contracts** | Public ports/protocols (`DataProvider`, `ExecutionProvider`, gateway/adapter protocols, capability model). New brokers implement contracts; do not fork them casually. |
| **Folder ownership** | Who owns which concern (`src/domain`, `application`, `brokers/*`, `tradex.runtime`, `infrastructure`, `api`, `cli`, `analytics`, `datalake`). |
| **Dependency rules** | Enforced by import-linter / architecture tests. No new upward imports; no new “temporary” ignores without expiry. |

**Product path (stable mental model):**

```text
tradex.connect(broker, mode=sim|market|trade)
  → Session
    → Universe / Instrument
      → DataProvider / OrderServicePort
        → broker adapters (hidden)
```

---

## 6. What is allowed to evolve

Everything not listed as frozen may evolve freely **inside modules already being touched** for a capability:

- Adapter internals (HTTP, WS, mapping, retries)
- CLI/API presentation layers
- Implementation details of OMS components (behind ports)
- Docs, examples, fitness tests
- Shims and deprecations (Boy Scout toward `tradex.runtime` / public ports)
- File splits, naming cleanup, dead-code deletion **in the blast radius of the feature**

Large structural moves require either:

1. a **Category A** production risk, or  
2. a **Category B** blocker for the current epic, or  
3. an approved epic plan that lists the move as a delivery enabler.

---

## 7. Issue classification (A / B / C)

| Class | Meaning | When to fix |
|-------|---------|-------------|
| **A — Production blocker** | Can lose money, leak secrets, corrupt ledger/PnL, break live signal→order path, break OMS correctness, break event correctness/idempotency. | Immediately; blocks release. |
| **B — Blocks feature delivery** | Duplication, giant modules, confusing ownership, or missing contracts that prevent shipping the current capability. | Only when working in that area for a feature. |
| **C — Engineering improvement** | Naming, folder polish, nicer abstractions, speculative cleanup. | Only as Boy Scout work inside modules already modified. Never a standalone ticket that pauses delivery. |

### Order placement environments

| Environment | Purpose | Gate |
|-------------|---------|------|
| **paper** (`mode=sim`) | Default CI / local development | Always safe |
| **sandbox** (`DHAN_ENVIRONMENT=SANDBOX` + allow-orders) | E2E place/modify/cancel without production money | `@pytest.mark.sandbox`; dedicated env file (e.g. `.env.dhan.sandbox`) |
| **live production** | Real capital | Process OMS + `ALLOW_LIVE_ORDERS=1` only under desk control |

Do **not** treat “no order placement in default CI” as “orders untested.” Prefer **sandbox** for broker write-path verification.

---

## 8. Definition of Done

A change is done only when **all** applicable items hold:

1. **User-visible or API-visible capability works** for the agreed slice (paper at minimum; live broker when the epic requires it).
2. **Category A risks** in the touched money/data path are closed or explicitly accepted with mitigation.
3. **Tests:** unit for logic, contract/integration where ports/adapters meet, regression for fixed bugs. Prefer tests that would fail if the capability regresses.
4. **Architecture:** import-linter / architecture fitness still pass; no new permanent layering violations.
5. **Docs:** public API docs/examples updated if the product surface changed; backlog item status updated.
6. **Deployable:** mainline remains green; no half-migrated public imports; no secrets committed.
7. **Boy Scout:** touched modules are cleaner (dup/dead code/naming/tests) without expanding scope into unrelated packages.

“Done” is **shippable**, not “perfect.”

---

## 9. Boy Scout Rule

> **Never leave a module worse than you found it.**

For every **touched** module (only):

- remove duplication that obscures the change  
- improve naming that misleads readers  
- improve or add tests for the behavior you changed  
- simplify logic you had to understand  
- remove dead code in the same file/package path  
- improve documentation that would have saved you time  

Do **not** use Boy Scout as a license to rewrite neighboring subsystems.

---

## 10. Continuous Engineering Loop

```text
Plan (capability + A/B blockers)
  → Pick one capability slice
    → Review architecture only as needed for that slice
      → Fix Category A blockers on the path
        → Remove duplication that blocks delivery
          → Improve APIs only if the product surface requires it
            → Add tests
              → Ship
                → Reassess backlog
                  → Repeat
```

**Ship is mandatory.** An iteration without a releasable increment is incomplete unless it closed a Category A production blocker.

---

## 11. Delivery-first mindset

### Do

- Keep the system deployable after every iteration  
- Prefer the smallest end-to-end slice that a user can run  
- Stabilize public APIs before expanding them  
- Refactor with measurable benefit (bug class closed, feature unblocked, boundary enforced)  
- Reduce debt incrementally through feature work  

### Do not

- Pause feature development for architectural perfection  
- Open multi-week pure-refactor programs  
- Create package-named epics (`brokers`, `analytics`) without a user capability  
- Expand freeze surfaces casually  
- “While I’m here” rewrite of uninvolved modules  

### AI / agent mission

Agents and contributors default to:

> Deliver production-ready capability slices continuously; improve architecture only through small, incremental, measurable changes in the modules required for that delivery.

Not:

> Build the perfect architecture first.

---

## 12. Planning before coding

For each new epic (or major slice):

1. Write or update an **implementation plan** (`reports/EPIC_NN_*_PLAN.md`).
2. Identify reusable components, modules to touch, Category A fixes, API freeze points, tests, risks, deliverables, acceptance criteria.
3. Get plan approval (human owner).
4. Only then implement the smallest shippable slice.
5. After ship: update Delivery Backlog; reassess next slice.

---

## 13. Relationship to other documents

| Document | Role under this constitution |
|----------|------------------------------|
| `docs/OPERATING_MODEL.md` | **This file** — how we work |
| `reports/ENGINEERING_BACKLOG.md` | Delivery backlog (epics + A/B/C items) |
| `reports/EPIC_*_PLAN.md` | Approved implementation plans |
| `docs/ARCHITECTURE.md` | Current system map (descriptive) |
| `docs/OBJECT_MODEL.md` | Public product API narrative |
| `docs/architecture-review/*` | Historical analysis / north-star designs — **not** automatic work queues |
| `reports/ARCHITECTURE_REVIEW_*.md` | Findings feed A/B/C classification; do not execute as pure refactor waves |

If a historical roadmap conflicts with this operating model, **this document wins for prioritization**.

---

## 14. One-page checklist (PR / iteration)

- [ ] Which epic / user capability does this serve?  
- [ ] Is any Category A risk introduced or left open?  
- [ ] Did we only refactor what the feature forced (plus Boy Scout in touch set)?  
- [ ] Are frozen surfaces preserved or explicitly versioned?  
- [ ] Tests prove the capability and prevent regression?  
- [ ] Backlog and docs updated?  
- [ ] Can we ship?

---

*End of Operating Model. When in doubt: ship a smaller correct slice.*
