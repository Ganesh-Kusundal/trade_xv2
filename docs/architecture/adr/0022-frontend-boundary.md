# ADR-0022: Frontend Boundary (Option B — Bounded Operator Surface)

## Status

Accepted — 2026-07-22

## Context

TradeXV2 needs a clear decision on where operators interact with the platform.
`web/` currently holds only `.env.example` — no React/TS SPA is implemented.
Building a full browser dashboard in Phase 4 would duplicate surfaces already
available via FastAPI and the `tradex` CLI/TUI, and would expand the security
and parity review surface without product need.

WebSocket endpoints (`/ws/market`, `/ws/market/{symbol}`, `/ws/replay/{session_id}`)
stream market and replay data to clients. When the API is exposed beyond localhost,
those streams must enforce the same auth policy as REST routes.

CORS for any future browser client must come from the single config source
([ADR-003](0003-single-config-source.md) — `AppConfig`), not ad-hoc middleware
values.

Operator REST hardening (process session singleton, no per-request `tradex.connect`,
production `AUTH_MODE` gate) is covered by Phase 4 R10 — see
[ADR-0020](0020-operator-api-hardening.md).

## Decision

**Option B (bounded):** document and ratchet the API + CLI/TUI operator path;
defer full SPA.

1. **Operator surfaces (in scope)**
   - **FastAPI** — `src/interface/api/` REST routers, health probes, OpenAPI docs,
     WebSocket market/replay feeds.
   - **tradex CLI** — `src/tradex/cli.py` Click commands (quote, ui, session, etc.).
   - **Textual TUI** — `src/interface/ui/` terminal UI over the same SDK/session
     wiring as CLI.

2. **SPA deferred (out of scope for Phase 4)**
   - `web/` remains a placeholder (`.env.example` only).
   - No Vite/React build, no SPA routing, no frontend CI gate until a future ADR
     explicitly lifts this boundary.

3. **WebSocket authentication**
   - When `AUTH_MODE=api_key`, every WebSocket handler must call
     `reject_ws_if_unauthorized()` before accepting the connection.
   - API key is validated via the `X-API-Key` **header only** (never query string).
   - When `AUTH_MODE=none` (local dev / pytest / `TRADEX_DEV=1` gate), WS connects
     without key — same policy as REST (`auth.py`).

4. **CORS**
   - Applied in `create_app()` via Starlette `CORSMiddleware`.
   - Origins, credentials, methods, and headers read from `AppConfig`
     (`TRADEX_CORS_ORIGINS`, `TRADEX_CORS_ALLOW_*` env vars).
   - Default origin `http://localhost:5173` reserved for a future local SPA dev
     server; no SPA is required for operator workflows today.

## Consequences

- Positive: single operator story (API + terminal); no premature frontend
  investment; WS auth ratchet prevents silent exposure of live feeds.
- Negative: no browser dashboard until a follow-on ADR; operators use curl,
  OpenAPI, CLI, or TUI.
- Ratchet: `tests/architecture/test_frontend_boundary.py` (ADR file exists; WS
  handlers call `reject_ws_if_unauthorized`).

## References

- [ADR-0020](0020-operator-api-hardening.md) — operator REST/session/auth hardening (R10)
- [ADR-003](0003-single-config-source.md) — `AppConfig` / CORS fields
- `context/architecture.md` — interface layer boundary
- `src/interface/api/auth.py` — `reject_ws_if_unauthorized`
- `src/interface/api/ws/market.py`, `src/interface/api/ws/replay.py`
