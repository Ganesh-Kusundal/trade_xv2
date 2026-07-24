# Broker Gateway: Token + Instrument-Master Hardening Plan

> **For Hermes:** Use subagent-driven-development to implement task-by-task (TDD each).

**Goal:** Fix the correctness bugs in the Gateway/Connection token + instrument-master lifecycle that the code review surfaced, and make the "auto-refresh" behavior actually work, without widening the broker's public surface.

**Architecture:** `Gateway → Connection → {HttpTransport + TokenManager + *InstrumentAdapter + wire}`. Tokens are probe-before-mint with disk+memory reuse; the scrip master is a tokenless CDN download with a 6h on-disk cache, lazy single-flight load, and a daily background scheduler. All confirmed against source this session.

**Tech Stack:** Python 3.14 (uv), pytest, stdlib only (urllib, threading). No new dependencies.

---

## Findings (verified against source, not assumption)

### 🔴 Bug 1 — `force_refresh` is silently dropped (daily scheduler is a no-op for re-download)
`master_lifecycle.InstrumentRefreshScheduler.refresh_now()` calls `self._master.ensure_fresh(force_refresh=True)` (master_lifecycle.py:84). That reaches `DhanConnection.ensure_fresh(force_refresh=True)` (connection.py:151), which **clears `_instruments_loaded` but then calls `self.instruments.load_instruments()` with NO argument** (connection.py:165). `DhanInstrumentAdapter.load_instruments(self)` (dhan/adapters/instruments.py:89) and the Upstox twin **have no `force_refresh` parameter**. So the adapter only re-downloads when the *disk file* is >6h old; the scheduler's intent (force a fresh pull) is discarded. Within the TTL window the daily tick just re-parses disk. The "daily refresh" feature does not refresh.

### 🔴 Bug 2 — malformed JWT is trusted forever
`common/jwt_expiry.py:parse_expiry_epoch` returns `-1.0` on any decode failure (line 25). `_token_usable` / `_access_token_usable` then hit the fallback `return True` (auth.py:101, 110) — "non-JWT static token: usable until broker_rejected". A truncated/corrupt token that *looks* like a JWT but won't decode therefore gets used indefinitely and only fails at the broker. Should force a refresh instead of trusting.

### 🟡 Improvement A — `connect()` blocks the caller on a 28 MB sync download
`DhanGateway.connect()` → `ensure_fresh()` (gateway.py:60-65). On a cold cache this synchronously downloads the 28 MB Dhan CSV (or 3.6 MB Upstox gz) on the **caller's thread**. In a live trading loop `connect()` can hang seconds–minutes. The lazy path is fine, but the *proactive* warm-load on `connect()` should not block.

### 🟡 Improvement B — no health signal for "token about to expire"
`TokenRefreshScheduler` (token_lifecycle.py:88) calls `ensure_token()` every 300 s; it's a no-op unless inside the 300 s buffer. There's no `is_expiring_soon()` the Gateway can surface via `mass_status()`/`check_connection()` so the app can warn before a mid-session expiry.

### 🟢 Parity (optional) — `search()` is substring-only
`DhanInstrumentAdapter.search` (instruments.py:410) and Upstox twin match on `symbol`/`instrument_id` substrings only. src had alias/ISIN keys via `generate_alternate_keys`; v2 registers only `wire` refs. Not on the critical path; defer unless you want it.

---

## Step-by-step plan

### Task 1: Thread `force_refresh` through to the adapters (fixes Bug 1)
**Objective:** Make the daily scheduler able to actually re-download the master.
**Files:**
- Modify: `src/plugins/brokers/dhan/adapters/instruments.py:89` (`load_instruments`)
- Modify: `src/plugins/brokers/upstox/adapters/instruments.py:96` (`load_instruments`)
- Modify: `src/plugins/brokers/dhan/connection.py:165` (`ensure_fresh`)
- Modify: `src/plugins/brokers/upstox/connection.py` (`ensure_fresh`)
- Test: `tests/unit/plugins/brokers/test_instrument_refresh.py` (new)

**Step 1: Write failing test** — scheduler `force_refresh=True` re-downloads even when cache is fresh:
```python
def test_force_refresh_redownloads_within_ttl(tmp_path, monkeypatch):
    # Seed a fresh cache
    cache = tmp_path / "dhan-instruments-2026-07-24.csv"
    cache.write_text("SEM_EXM_EXCH_ID,SEM_SEGMENT,...\n" + "NSE,E,RELIANCE,1333\n" * 12000)
    monkeypatch.setattr(adapters, "_RUNTIME_DIR", tmp_path)
    dl = []
    monkeypatch.setattr(DhanInstrumentAdapter, "_download_csv", lambda self, u: dl.append(u) or SAMPLE_CSV)
    adapter = DhanInstrumentAdapter(transport=FakeTransport(), wire=DhanWire())
    adapter.load_instruments()          # cache hit, no download
    assert dl == []
    adapter.load_instruments(force_refresh=True)  # MUST re-download
    assert dl == [DHAN_INSTRUMENT_CSV]
```

**Step 2: Run, expect FAIL** (`load_instruments() got unexpected keyword` or no re-download).
**Step 3: Implement** — add `force_refresh: bool = False` param to both adapters' `load_instruments`; in `load_from_csv`/`_load_with_cache` treat `force_refresh=True` as `force_refresh=True` for the TTL check (skip the age gate). In both connections' `ensure_fresh`, pass it through: `self.instruments.load_instruments(force_refresh=force_refresh)`.
**Step 4: Run, expect PASS.**
**Step 5: Commit** — `git commit -m "fix: thread force_refresh to instrument adapters so daily scheduler re-downloads"`

### Task 2: JWT decode failure must not be trusted (fixes Bug 2)
**Objective:** A corrupt/unparseable token is forced to refresh, not used forever.
**Files:**
- Modify: `src/plugins/brokers/common/jwt_expiry.py:12` (`parse_expiry_epoch`)
- Modify: `src/plugins/brokers/dhan/auth.py:87` + `upstox/auth.py:94` (`_token_usable`/`_access_token_usable`)
- Test: `tests/unit/plugins/brokers/test_jwt_expiry.py` (new)

**Step 1: Write failing test** — `parse_expiry_epoch("not-a-jwt")` returns `-1`, and `_token_usable("garbage.jwt.here")` with no store expiry is `False` (not True).
**Step 2: Run, expect FAIL** (currently returns `True`).
**Step 3: Implement** — keep `parse_expiry_epoch` returning `-1` for "no info", but in the usability helpers distinguish *"has JWT structure but unparseable"* from *"no JWT at all"*: if the string looks like a JWT (2 dots) but decode fails, return `False`; only a genuinely absent/empty token falls through to the static-token-usable branch. Simplest: change helper to `return False` when `jwt_exp == -1 and token_contains_two_dots`.
**Step 4: Run, expect PASS.**
**Step 5: Commit** — `git commit -m "fix: reject unparseable JWTs instead of trusting them"`

### Task 3: Make `connect()` warm-load non-blocking (Improvement A)
**Objective:** `connect()` returns immediately; the proactive master load runs in a background thread; data calls still lazy-trigger.
**Files:**
- Modify: `src/plugins/brokers/dhan/gateway.py:60` (`connect`)
- Modify: `src/plugins/brokers/upstox/gateway.py:57` (`connect`)
- Test: extend `tests/unit/plugins/brokers/test_gateway_data_probe.py`

**Step 1: Write failing test** — `connect()` returns within a tight timeout even with a cold cache (patch `load_instruments` to sleep 2 s; assert `connect()` returns in <0.5 s and the scheduler/thread eventually loads).
**Step 2: Run, expect FAIL** (currently blocks).
**Step 3: Implement** — in `connect()`, spawn `threading.Thread(target=self.ensure_fresh, daemon=True).start()` instead of a synchronous `self.ensure_fresh()`. Keep the synchronous lazy call in each data/order method (first real call still blocks until loaded — acceptable, same as today).
**Step 4: Run, expect PASS.**
**Step 5: Commit** — `git commit -m "perf: run proactive master warm-load off the connect() caller thread"`

### Task 4: Expiry health signal (Improvement B)
**Objective:** Gateway can report token-expiry risk via `mass_status()`.
**Files:**
- Add: `is_expiring_soon(self, *, within: float | None = None)` to `DhanTokenManager` (auth.py:168) and `UpstoxTokenManager` (auth.py:148), delegating to `JwtExpiry` + `refresh_buffer_seconds`.
- Modify: `DhanGateway`/`UpstoxGateway` `mass_status()` to include `token_expiring_soon: bool` in the snapshot (or add `connection.token_status()`).
- Test: `tests/unit/plugins/brokers/test_token_health.py` (new)

**Step 1: Write failing test** — manager with a JWT expiring in 60 s reports `is_expiring_soon() is True` (buffer 300 s).
**Step 2: Run, expect FAIL.**
**Step 3: Implement** the method; wire into `mass_status`.
**Step 4: Run, expect PASS.**
**Step 5: Commit** — `git commit -m "feat: expose token-expiry health signal via mass_status"`

### Task 5: Regression sweep + ruff
**Objective:** Confirm nothing regressed and lint is clean.
**Files:** run, don't edit.
- Run: `uv run --extra dev ruff check src tests`
- Run: `PYTHONPATH=$(echo "$PYTHONPATH" | tr ':' '\n' | grep -v hermes-agent | paste -sd ':' -) uv run --extra dev python -m pytest tests/unit/plugins/brokers/ -q`

**Step 1–4:** ruff = 0 findings; broker suite green (incl. new tests from Tasks 1–4).
**Step 5: Commit** if any fixtures changed.

---

## Risks / tradeoffs
- **Task 1** changes `load_instruments` signature — but it's only called from `Connection.ensure_fresh` (internal) + the explicit `gateway.load_instruments()` public method. The public method's callers don't pass the kwarg, so it stays backward-compatible (default `False`). No Protocol widened.
- **Task 2** could, in a pathological case, cause one extra mint where before it reused a "valid-looking" token. That's the *desired* behavior (don't trust garbage).
- **Task 3** — first `ltp()` after a cold `connect()` may still block briefly (lazy path unchanged). That's fine; the hang-on-`connect()` regression is gone.
- **Deferred:** alias/ISIN `search()` (Parity, 🟢) — only do if you want it; not on the critical path.

## Open questions
1. Do you want `connect()` to *wait* for the warm-load if a caller needs instruments ready immediately (add `connect(blocking_warm_load=False)`), or is fire-and-forget always fine?
2. Should the daily instrument scheduler also re-download the **MCX supplement** on force (currently `_fetch_mcx_supplement` is called on every `load_from_csv`, so yes — already covered once Bug 1 is fixed).
