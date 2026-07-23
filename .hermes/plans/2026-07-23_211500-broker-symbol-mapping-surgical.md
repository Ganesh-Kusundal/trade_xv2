# Broker Symbol-Mapping — Surgical Reconciliation (v2-native)

> **For Hermes:** Use subagent-driven-development skill to implement this plan task-by-task.

**Goal:** Remove the dead/divergent instrument-resolution code in v2 and implement a
*clean, minimal* symbol-resolution flow that respects v2's flat design — adding only the
two real behaviors the architecture spec mandates that v2 currently lacks: **index
fallback** and **symbol-suffix normalization**. No new DTOs, no `BrokerInstrumentService`
Protocol sprawl, no legacy 4-layer port.

**Architecture (proposed, v2-respecting):**

v2's live flow is already clean and flat:

```
Gateway(InstrumentId) → Adapter → Wire.security_id(iid)/instrument_key(iid)
                                        ↓
                              Resolver.resolve_ref(iid) → BrokerWireRef(wire=…)
```

`InstrumentId` (`EXCHANGE:UNDERLYING[:…]`) IS the canonical identity — used by every
layer. The spec's `ResolvedInstrument(symbol, exchange)` string-pair shape is a *legacy*
convention and would be a regression for v2; we keep `InstrumentId`-based carriers.

The single resolution store is `InMemoryInstrumentResolver` (already exists, alias
fan-out done this session). We:
1. **Remove dead surface**: `resolver.search()` and `resolver.resolve()` (neither is
   called in the live flow — gateways call `adapter.search()`; nothing calls
   `resolve()`). Shrink the `BrokerInstrumentService` Protocol to what's used.
2. **Add index fallback** to `resolve_ref`: on cache miss, consult a broker-injected
   `index_fallback(iid) -> dict | None` (Dhan → `index_map` security_id; Upstox →
   `index_upstox_key`). Returns a `BrokerWireRef` so `security_id("NSE:NIFTY")` works
   even when the master isn't loaded (spec §5.3 step 6 / §2).
3. **Add suffix-strip normalization** (spec §3.1): `RELIANCE-EQ` → `RELIANCE` at both
   `register` and `resolve_ref` time, so suffixed symbols resolve. A single small
   `_strip_symbol_suffix` helper (reject path-traversal, strip `-EQ/-BE/…`).

This is the *entire* change. It honors the spec's *behavior* without importing its
structure.

**Tech Stack:** Python 3.13, stdlib (`re`). Test runner: project venv.
**Mandatory env prefix** `env -u PYTHONPATH` (shell PYTHONPATH shadows venv with py3.11).

---

## Current-state audit (evidence — what to remove vs keep)

**KEEP (live path, correct):**
- `domain/value_objects/__init__.py::InstrumentId` — canonical identity + factories.
- `domain/symbols.py` — `normalize_symbol` etc.
- `common/instruments_keys.py` — `generate_alternate_keys` (alias wheel).
- `common/index_map.py` — `_IndexEntry`, `get_index_entry`, `index_upstox_key`, `is_index`.
- `common/instruments.py::InMemoryInstrumentResolver` — `register`/`load_from_rows`/
  `resolve_ref`/`reverse` (alias fan-out already implemented).
- `DhanWire.security_id()` / `UpstoxWire.instrument_key()` — the resolution entry points.

**REMOVE (dead / divergent, shrinks surface):**
- `InMemoryInstrumentResolver.search()` — unused (gateways call `adapter.search()`).
- `InMemoryInstrumentResolver.resolve()` + its external `ResolvedInstrument` exposure in
  the Protocol — unused in live flow.
- The `BrokerInstrumentService` Protocol's `search`/`resolve` stub lines (keep
  `load`/`resolve_ref`/`is_loaded`/`stats` only; v2 uses method names `register`/
  `load_from_rows`, not `load`).

**ADD (the two real gaps):**
- Index-fallback injection + logic in `resolve_ref`.
- Suffix-strip normalization in `register` + `resolve_ref`.

---

## Task 1: Strip symbol suffixes at register + resolve (spec §3.1)

**Objective:** `RELIANCE-EQ` → `RELIANCE` so suffixed symbols normalize and match.

**Files:**
- Modify: `v2/src/plugins/brokers/common/instruments.py` (add `_strip_symbol_suffix`, use in `register` + `_alias_keys` symbol source + `resolve_ref` miss path)
- Test: `v2/tests/unit/plugins/brokers/test_instrument_mapping.py` (extend)

**Step 1: Write failing test**

```python
def test_suffix_strip_on_register_and_resolve():
    from plugins.brokers.common.instruments import InMemoryInstrumentResolver
    r = InMemoryInstrumentResolver()
    r.register(InstrumentId.parse("NSE:RELIANCE-EQ"), {"security_id": "2885"},
               symbol="RELIANCE-EQ", exchange="NSE")
    # resolve via canonical stripped form
    assert r.resolve_ref(InstrumentId.parse("NSE:RELIANCE")).require("security_id") == "2885"
```

**Step 2: Run** `env -u PYTHONPATH .../venv/bin/python -m pytest tests/unit/plugins/brokers/test_instrument_mapping.py -q` → FAIL (key stored as `NSE:RELIANCE-EQ`, lookup `NSE:RELIANCE` misses).

**Step 3: Implement** — add helper:
```python
import re
_SUFFIX = re.compile(r"[-_](EQ|BE|BL|BZ|MC|NC|NZ|SM|SO|TT)\s*$", re.IGNORECASE)
def _strip_symbol_suffix(sym: str) -> str:
    sym = sym.strip().upper()
    return _SUFFIX.sub("", sym)
```
Use it when deriving `symbol` in `register` (default derivation) and when building alias
keys (pass `symbol=_strip_symbol_suffix(meta.symbol)` into `generate_alternate_keys`), and
in `resolve_ref` miss fallback (try stripped `instrument_id` with suffix removed).

**Step 4: Run → PASS. Step 5: commit** `fix(common): strip exchange suffixes in resolver`.

---

## Task 2: Index fallback in `resolve_ref` (spec §5.3 step 6 / §2)

**Objective:** `security_id("NSE:NIFTY")` returns the index's wire id even when the master
isn't loaded, via a broker-injected fallback.

**Files:**
- Modify: `v2/src/plugins/brokers/common/instruments.py` (`__init__` accepts
  `index_fallback: Callable[[InstrumentId], dict | None] | None`; `resolve_ref` miss path
  calls it)
- Modify: `v2/src/plugins/brokers/dhan/wire.py` (pass `index_fallback` using `index_map`
  dhan security_id), `v2/src/plugins/brokers/upstox/wire.py` (pass `index_upstox_key`)
- Test: `v2/tests/unit/plugins/brokers/test_instrument_mapping.py`

**Step 1: Write failing test**

```python
def test_index_fallback_on_cache_miss():
    from plugins.brokers.common.instruments import InMemoryInstrumentResolver
    def fb(iid):
        if str(iid).startswith("NSE:NIFTY"):
            return {"security_id": "13"}
        return None
    r = InMemoryInstrumentResolver(index_fallback=fb)
    assert r.resolve_ref(InstrumentId.parse("NSE:NIFTY")).require("security_id") == "13"
    # unknown still raises
    import pytest
    with pytest.raises(KeyError):
        r.resolve_ref(InstrumentId.parse("NSE:GHOST"))
```

**Step 2: Run → FAIL (no fallback arg / raises on miss).**

**Step 3: Implement** — in `__init__`: `self._index_fallback = index_fallback`. In
`resolve_ref`, after the canonical + normalized miss, before raising:
```python
if self._index_fallback is not None:
    wire = self._index_fallback(instrument_id)
    if wire is not None:
        return BrokerWireRef(instrument_id=instrument_id, wire=wire)
```
Wire side (Dhan):
```python
from plugins.brokers.common.index_map import get_index_entry, is_index
def _dhan_index_fallback(iid):
    sym = iid.underlying
    if is_index(sym):
        e = get_index_entry(sym)
        if e and e.dhan_security_id:
            return {"security_id": e.dhan_security_id, "exchange_segment": e.dhan_segment or "IDX_I"}
    return None
self._resolver = InMemoryInstrumentResolver(index_fallback=_dhan_index_fallback)
```
Upstox analog using `index_upstox_key`.

**Step 4: Run → PASS. Step 5: commit** `feat(common): index fallback in resolve_ref`.

---

## Task 3: Remove dead surface (`search`/`resolve` + Protocol trim)

**Objective:** Shrink resolver to the live API only.

**Files:**
- Modify: `v2/src/plugins/brokers/common/instruments.py` (delete `search()` method; delete
  `resolve()` method; keep `ResolvedInstrument` ONLY as the internal `_meta` dataclass —
  not Protocol-exposed; trim `BrokerInstrumentService` Protocol to
  `register`/`load_from_rows`/`resolve_ref`/`reverse`/`is_loaded`/`stats`)
- Test: `v2/tests/unit/plugins/brokers/test_instruments.py` (remove/adjust any test that
  calls `resolver.search`/`resolver.resolve` — those tests are testing dead code)

**Step 1: Confirm no live caller** (already verified: gateways call `adapter.search`,
nothing calls `resolver.resolve`/`resolver.search`).

**Step 2: Delete the two methods + trim Protocol. Step 3: Run full suite**
`env -u PYTHONPATH .../venv/bin/python -m pytest tests/unit/plugins/brokers -q` → must
stay green (any test exercising `search`/`resolve` must be deleted as it tested dead code).

**Step 4: commit** `refactor(common): remove dead resolver.search/resolve`.

---

## Task 4: Wire the fallback end-to-end + full regression

**Objective:** Verify `NIFTY`/`NIFTY50`/`BANKNIFTY`/`RELIANCE-EQ` resolve through the real
Wire (not just the resolver unit).

**Files:**
- Test: `v2/tests/unit/plugins/brokers/test_instrument_mapping.py` (integration via Wire)
- Verification only elsewhere

**Step 1: Write failing test** (DhanWire with index fallback):
```python
def test_dhan_wire_resolves_index_without_master():
    from plugins.brokers.dhan.wire import DhanWire
    w = DhanWire()  # no master loaded
    ref = w.security_id(InstrumentId.parse("NSE:NIFTY"))  # index fallback
    assert ref == "13"
```
(Adapt to DhanWire's actual `security_id` return shape — it returns the id string today;
if it returns via `resolve_ref().require`, this works once Task 2 wires the fallback.)

**Step 2: Run → FAIL (raises today). Step 3: ensure Task 2 wiring makes it PASS.
Step 4: Run full suite** `env -u PYTHONPATH .../venv/bin/python -m pytest tests/unit/plugins -q`
→ expect all green (449 prior + ~6 new).

---

## Verification (end of plan)

```bash
cd /Users/apple/Downloads/Trade_XV2/v2 && env -u PYTHONPATH /Users/apple/Downloads/Trade_XV2/venv/bin/python -m pytest tests/unit/plugins -q
```
Expected: all green. Optional live gateway probe (user mandate — gateway only):
```bash
env -u PYTHONPATH PYTHONPATH=src .../venv/bin/python -m tradex.check_connection --broker dhan
```
then resolve `NIFTY`, `NIFTY50`, `BANKNIFTY`, `RELIANCE-EQ` through the Dhan/Upstox wire
and assert non-None wire refs.

## Risks / Tradeoffs / Open questions

- **We deliberately do NOT adopt the spec's `ResolvedInstrument(symbol, exchange)` /
  `BrokerInstrumentService` Protocol / per-broker `SymbolResolver` DTOs** — they are
  legacy 4-layer structure that fights v2's flat `InstrumentId`-centric design. v2's
  `resolve_ref → BrokerWireRef` already satisfies the spec's *intent* (opaque wire ref,
  gateway never reads it). Confirm this restraint matches your "don't increase complexity"
  directive.
- **Preference rules** (EQUITY>FUTURE>OPTION at load time): legacy applies these during
  bulk load; v2's alias fan-out uses last-write-wins. This plan does NOT add load-time
  preference (out of scope, YAGNI for the current flow). Note in code if needed.
- **Suffix strip regex** covers the 10 common NSE/BSE suffixes from spec §3.1; extend the
  alternation if more surfaces appear.
