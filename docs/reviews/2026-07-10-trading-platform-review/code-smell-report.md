# Code Smell Report

The issue is not lack of abstractions. It is that the same responsibility is represented by multiple abstractions with no enforced owner.

## Critical and high findings

### C1 — Execution semantics duplicated across modes

`src/application/oms`, `src/analytics/replay`, `src/analytics/paper`, and `src/brokers/paper` each own parts of order, fill, position, or PnL behavior. This is shotgun surgery: a change to slippage, fill timing, or status semantics can require updates in several unrelated paths. Replace with one execution ledger/projector and mode-specific event/fill sources.

### C2 — Broker gateways are god objects

`src/brokers/upstox/broker.py:79-154` wires settings, auth, instruments, clients, adapters, reconciliation, PnL, and capabilities. `src/brokers/upstox/gateway.py:57-106` composes another adapter graph. Dhan's connection similarly wires roughly twenty collaborators (`src/brokers/dhan/streaming/connection.py:70-124`). Move composition to one explicit root and expose typed ports.

### C3 — HTTP request methods mix unrelated policies

`src/brokers/dhan/api/http_client.py:409-582` combines auth refresh, circuit breaking, rate limiting, retries, parsing, metrics, and error translation. The async client duplicates this responsibility (`src/brokers/dhan/api/async_http_client.py:172-338`). Extract one operation-aware request policy and separate transport, auth, retry decision, and response decoding.

### C4 — Reconnect mechanism is duplicated and divergent

Dhan depth, Dhan API, Upstox WebSocket, and common transport each own reconnect behavior (`src/brokers/dhan/data/depth_feed_base.py:404-422`, `src/brokers/dhan/api/reconnecting_service.py:136-184`, `src/brokers/upstox/websocket/v3_auto_reconnect.py`, `src/brokers/common/transport.py`). The new kernel is not yet the sole runtime owner.

### H1 — Raw dict leakage and broker-shaped domain models

`src/brokers/dhan/gateway.py:247-342` and `src/brokers/upstox/gateway.py:239-243` expose dict-shaped results. Upstox tick translation returns raw payloads on resolution failure (`src/brokers/upstox/adapters/tick_translator.py:47-63`). Enforce ACL translation at the port boundary and represent unknown/pending states explicitly.

### H2 — Failure handling is lossy

Broad exception handlers return `None`, empty frames, empty chains, zero balances, or empty positions in Dhan, Upstox, datalake, and historical services. Examples: `src/brokers/dhan/data/data_provider.py:49-58`, `src/datalake/gateway.py:154-180`, `src/infrastructure/historical_data.py:105-134`. This is a semantic smell, not merely error handling. Use typed result/error states with freshness and provenance.

### H3 — Capability and exchange vocabulary is duplicated

Capability frozensets, segment maps, broker capability objects, and market surface declarations coexist. Upstox has separate capability shapes (`src/brokers/upstox/broker.py:380-414`, `src/brokers/upstox/gateway.py:220-221`). Keep one declarative capability SSOT and validate executable support against it.

### H4 — Feature ownership is fragmented

Dhan super/forever orders span `execution`, `extensions`, `extended.py`, and common extensions; Upstox GTT/exit-all behavior spans multiple adapters and extension modules. Move orchestration into broker-agnostic use cases; keep wire differences in adapters.

### H5 — Private collaborator reaches

Runtime and gateways inspect private fields (`src/runtime/trading_runtime_factory.py:93-100`, `src/brokers/upstox/gateway.py:244-256`). This hides dependency ownership and makes refactoring unsafe. Public typed ports should be the only cross-boundary interface.

### H6 — Paper broker is a second OMS

`src/brokers/paper/paper_orders.py:243-361` implements its own order/position flow, bypassing shared validation/idempotency. Paper should be a transport/fill model behind the same OMS, not a parallel OMS.

## Medium findings

- `extended.py` has different meanings in Dhan and Upstox; names collide while responsibilities do not (`src/brokers/dhan/extended.py`, `src/brokers/upstox/extended.py`/`extras.py`).
- Raw decimal conversion is repeated in adapters instead of one price decoder.
- `DataLakeGateway` implements a broad broker-like contract while throwing `NotImplementedError` for trading operations (`src/datalake/gateway.py:182-202`).
- Test and production paths sometimes scan `brokers` instead of `src/brokers`, making architecture checks vacuous.
- Module-level API dependencies and auth state create hidden process-global mutable state (`src/interface/api/deps.py:28-83`, `src/interface/api/auth.py:55-76`).
- The package contains useful import-linter rules, but numerous explicit ignores document residual violations rather than proving the boundary is clean (`pyproject.toml:296-492`).

## Refactoring principle

Do not fix these by adding more wrappers around the existing gateways. First establish ownership:

`typed domain port → one broker ACL → one execution ledger → one projector → one reconciliation control`

Then remove duplicate gateways and mode-specific shadow state as each broker migrates.
