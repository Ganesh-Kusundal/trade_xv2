# Production Readiness Scorecard

Scores reflect the current working tree, not the intended target architecture. A score of 1 means foundational controls are absent; 10 means independently evidenced production readiness.

## Scores

- **Architecture: 4/10.** Clear package/layer intent and a promising broker kernel, but duplicate gateways, private reaches, and mode-specific state remain.
- **Quant design: 3/10.** Strong research vocabulary and strategy infrastructure, but look-ahead risk, invalid scanner metrics, non-concurrent portfolio simulation, and parity gaps block trust.
- **Code quality: 4/10.** Large test and domain surface, but god objects, duplicated policies, raw dict leakage, and broad exception handling are widespread.
- **Testing: 4/10.** Broad taxonomy and many suites, but optional live tests, stale paths, vacuous architecture scans, and non-blocking gates undermine signal.
- **Reliability: 3/10.** Retries, health, reconnect, alerts, and reconciliation exist, but ownership and failure semantics are fragmented.
- **Scalability: 3/10.** Synchronous dispatch, process-global state, shared queues, and SQLite single-writer assumptions limit scale.
- **Security: 3/10.** Authentication and secret abstractions exist, but unsigned token ingestion, plaintext fallback, weak authorization, and non-durable audit are live blockers.
- **Performance: 4/10.** Benchmarks and telemetry exist, but no enforced capacity budgets and synchronous hot paths are demonstrated safe.
- **Maintainability: 4/10.** The repository is structured and documented, but duplicate ownership and compatibility shims make changes risky.
- **Operational readiness: 3/10.** Health/metrics/CI workflows exist, but green status does not reliably prove tradability or recovery.

## Overall production readiness

**3.5/10 — not production-ready for unattended real-money trading.**

Confidence: **high** for source-level architectural and semantic findings; **medium** for runtime throughput and deployment behavior because no production topology or sustained live-broker test was supplied.

## Release classification

- **Blocks live trading:** parity, ambiguous order writes, incomplete reconciliation, unsafe failure defaults, auth/RBAC/secrets, stale-data handling, and emergency-exit policy.
- **Blocks scaling:** synchronous event path, queue loss without resync, SQLite topology, shared mutable process state, and missing capacity budgets.
- **Quality debt:** naming collisions, documentation drift, duplicate adapters, and non-critical UI polish after control-plane risks are addressed.

## Evidence limitations

This assessment does not invent live market data or submit orders. Broker behavior, exchange semantics, real latency, deployment isolation, and secret-manager integration remain unverified until exercised in a controlled read-only/sandbox environment.
