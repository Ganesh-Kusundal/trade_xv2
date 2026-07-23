# Broker Symbol-Mapping Reconciliation Plan (v2 ↔ architecture spec)

> **For Hermes:** Use subagent-driven-development skill to implement this plan task-by-task.

**Goal:** Reconcile v2's `plugins/brokers` symbol-mapping layer to the authoritative
architecture spec `docs/architecture/broker-symbol-mapping.md` — correct the divergent
carrier/Protocol shapes, add the missing segment/exchange enums + index registry
coverage, and reimplement the spec's progressive resolution fallback + index fallback
per broker. Keep v2's flatter architecture (Gateway→Connection→Adapters); do NOT
blindly port the legacy 4-layer DTO machinery (`DhanInstrument`/`UpstoxInstrumentDefinition`).

**Architecture:** v2 keeps its single `InMemoryInstrumentResolver` (alias fan-out already
done) but gains: (1) `ExchangeSegment`/`Exchange` enums + `exchange_segments.py` alias
table; (2) doc-shaped `ResolvedInstrument`/`BrokerWireRef`/`LoadStats` carriers and the
doc-signature `BrokerInstrumentService` Protocol; (3) a **shared fallback resolver**
(`resolve_with_fallback`) that encodes the spec's 6-step (Dhan) / 4-step (Upstox)
progressive lookup + index fallback, parameterized per broker; (4) complete index
registry (35+ indices, `dhan_segment`/`upstox_segment`/`canonical_name` fields).

**Tech Stack:** Python 3.13, stdlib only (`re`, `functools`). Test runner: project venv.
**Mandatory env prefix** `env -u PYTHONPATH` (shell PYTHONPATH shadows venv with py3.11).

---

## Current-state inventory (read before planning — what exists in v2)

**KEEP (already matches spec):**
- `domain/value_objects/__init__.py::InstrumentId` — canonical `EXCHANGE:UNDERLYING[:YYYYMMDD[:STRIKE[:RIGHT]]]` + `equity/index/future/option/parse` factories (spec §1.1). ✅
- `domain/symbols.py` — `normalize_symbol`/`normalize_exchange`/`make_position_key` (spec §1.2). ✅
- `plugins/brokers/common/instruments_keys.py` — `generate_alternate_keys` (spec §4.3). ✅
- `plugins/brokers/common/index_map.py` — `_IndexEntry` with NIFTY/BANKNIFTY/SENSEX + `index_upstox_key` (spec §2, partial). ✅ but needs full coverage + `dhan_segment`/`upstox_segment` fields.

**REMOVE / CORRECT (diverges from spec):**
- `common/instruments.py::ResolvedInstrument` shape `(instrument_id, exchange, symbol, …)` → change to spec `(symbol, exchange, instrument_type, lot_size, tick_size, expiry, strike, option_type, underlying, canonical_symbol, name)`.
- `common/instruments.py::BrokerWireRef` shape `(instrument_id, wire)` → spec `(symbol, exchange, wire)`.
- `common/instruments.py::LoadStats` `(total, source)` → spec `(total, skipped, skip_rate, source)`.
- `BrokerInstrumentService` Protocol: `resolve(instrument_id)`, `resolve_ref(instrument_id)`, `search(query, limit=20)->list[dict]` → spec `resolve(symbol, exchange)`, `resolve_ref(symbol, exchange, expected_segment=None)`, `search(query, exchange=None)->list[ResolvedInstrument]`.
- Generic `InMemoryInstrumentResolver` has **no progressive fallback / preference rules / index fallback** (spec §5.3/§6.4) — reimplement via shared helper.

**ADD (missing in v2):**
- `domain/exchange_segments.py` — `ExchangeSegment` enum (NSE_EQ, BSE_EQ, NSE_FNO, BSE_FNO, MCX_COMM, NSE_CURRENCY, BSE_CURRENCY, IDX_I) + 18-alias table + helpers (spec §1.3).
- `Exchange` / `ExchangeId` / `InstrumentType` / `OptionType` enums — v2 has `ExchangeId`/`InstrumentType`/`OptionType` in `domain/enums.py` but **no `Exchange` short-code enum and no `ExchangeSegment`**. Add `ExchangeSegment` + `Exchange`.
- Per-broker segment mappers (spec §5.2 Dhan `_DHAN_WIRE`/`_EXCHANGE_SHORT`/`SEGMENT_TO_EXCHANGE`; §6.2 Upstox `_UPSTOX_TO_SEGMENT`/`_SEGMENT_TO_UPSTOX`).
- `config/indices.py` equivalent — expand `index_map.py` to full 35+ registry with all spec fields + `INDEX_TO_FNO_EXCHANGE` routing.

---

## Task 1: Add `ExchangeSegment` + `Exchange` enums and `exchange_segments.py` (spec §1.3)

**Objective:** Single source of truth for segment↔exchange conversion used by both brokers.

**Files:**
- Create: `v2/src/domain/exchange_segments.py`
- Modify: `v2/src/domain/enums.py` (add `ExchangeSegment`, `Exchange` if absent)
- Test: `v2/tests/unit/plugins/brokers/test_exchange_segments.py`

**Step 1: Write failing test**

```python
from domain.exchange_segments import ExchangeSegment, parse_segment, wire_value, canonical_exchange_short

def test_alias_resolution():
    assert parse_segment("NFO") == ExchangeSegment.NSE_FNO
    assert parse_segment("NSE_EQ") == ExchangeSegment.NSE
    assert wire_value(ExchangeSegment.NSE_FNO) == "NSE_FNO"
    assert canonical_exchange_short(ExchangeSegment.NSE_FNO) == "NFO"
```

**Step 2: Run** `env -u PYTHONPATH .../venv/bin/python -m pytest tests/unit/plugins/brokers/test_exchange_segments.py -q`
Expected: FAIL (module missing).

**Step 3: Implement** `exchange_segments.py` with the 18-entry `_ALIASES` dict and `_EXCHANGE_SHORT` from spec §1.3, plus `parse_segment`/`wire_value`/`canonical_exchange_short`/`is_*_segment` helpers.

**Step 4: Run → PASS. Step 5: commit** `feat(domain): add ExchangeSegment enum + alias table`.

---

## Task 2: Correct carrier shapes + `LoadStats` (spec §4.2)

**Objective:** Align `ResolvedInstrument`/`BrokerWireRef`/`LoadStats` to spec.

**Files:**
- Modify: `v2/src/plugins/brokers/common/instruments.py`
- Test: extend `v2/tests/unit/plugins/brokers/test_instruments.py`

**Step 1: Write failing test**

```python
def test_resolved_instrument_shape():
    from plugins.brokers.common.instruments import ResolvedInstrument
    r = ResolvedInstrument(symbol="RELIANCE", exchange="NSE", instrument_type="EQUITY",
                           canonical_symbol="RELIANCE")
    assert r.symbol == "RELIANCE" and r.exchange == "NSE" and r.canonical_symbol == "RELIANCE"

def test_broker_wire_ref_shape():
    from plugins.brokers.common.instruments import BrokerWireRef
    ref = BrokerWireRef(symbol="RELIANCE", exchange="NSE", wire={"security_id": "2885"})
    assert ref.require("security_id") == "2885"
```

**Step 2: Run → FAIL (old shape uses `instrument_id`).**

**Step 3: Implement** — replace `ResolvedInstrument` dataclass fields with spec list; `BrokerWireRef(symbol, exchange, wire)`; `LoadStats(total, skipped, skip_rate, source)`. Keep `register`/`resolve_ref` storing by `instrument_id.value` internally but expose carriers by `(symbol, exchange)`. Update `resolve()` to build `ResolvedInstrument(symbol=..., exchange=...)`.

**Step 4: Run → PASS. Step 5: commit** `refactor(common): align carriers to spec §4.2`.

---

## Task 3: Align `BrokerInstrumentService` Protocol signature (spec §4.1)

**Objective:** `resolve(symbol, exchange)`, `resolve_ref(symbol, exchange, expected_segment=None)`, `search(query, exchange=None)->list[ResolvedInstrument]`.

**Files:**
- Modify: `v2/src/plugins/brokers/common/instruments.py` (`BrokerInstrumentService` Protocol)
- Test: `v2/tests/unit/plugins/brokers/test_instruments.py`

**Step 1: Write failing test** asserting the Protocol declares the spec signatures (use `runtime_checkable` + a dummy impl).

**Step 2: Run → FAIL. Step 3: Implement** — update Protocol method stubs. Keep `InMemoryInstrumentResolver` working: add `resolve(symbol, exchange)`, `resolve_ref(symbol, exchange, expected_segment=None)`, `search(query, exchange=None)` that delegate to existing internal index (keyed by `EXCHANGE:SYMBOL`).

**Step 4: Run → PASS. Step 5: commit** `refactor(common): align BrokerInstrumentService Protocol to spec`.

---

## Task 4: Complete index registry (spec §2)

**Objective:** Full 35+ index coverage with `dhan_segment`/`upstox_segment`/`canonical_name`/`dhan_security_id` + `INDEX_TO_FNO_EXCHANGE` routing.

**Files:**
- Modify: `v2/src/plugins/brokers/common/index_map.py`
- Test: `v2/tests/unit/plugins/brokers/test_index_registry.py`

**Step 1: Write failing test**

```python
from plugins.brokers.common.index_map import get_index_entry, index_upstox_key, is_index
def test_full_index_coverage():
    assert get_index_entry("NIFTY50").dhan_security_id == "13"
    assert index_upstox_key("NIFTY") == "NSE_INDEX|Nifty 50"
    assert is_index("BANKNIFTY") is True
    assert get_index_entry("SENSEX").upstox_segment == "BSE_INDEX"
```

**Step 2: Run → FAIL (partial coverage / missing fields).**

**Step 3: Implement** — expand `_IndexEntry` dataclass with `dhan_segment`, `upstox_segment`, `canonical_name`, `dhan_security_id`, `upstox_name`; populate all 35+ NSE/BSE/global indices from spec §2.2/§2.3; add `INDEX_TO_FNO_EXCHANGE`.

**Step 4: Run → PASS. Step 5: commit** `feat(common): complete index registry per spec §2`.

---

## Task 5: Per-broker segment mappers (spec §5.2, §6.2–6.3)

**Objective:** Bidirectional segment↔exchange/wire mapping for Dhan & Upstox.

**Files:**
- Create: `v2/src/plugins/brokers/dhan/segments.py` (DhanSegmentMapper + `_DHAN_WIRE`/`_EXCHANGE_SHORT`/`SEGMENT_TO_EXCHANGE`)
- Create: `v2/src/plugins/brokers/upstox/segments.py` (`_UPSTOX_TO_SEGMENT`/`_SEGMENT_TO_UPSTOX` + helpers)
- Test: `v2/tests/unit/plugins/brokers/test_segment_mappers.py`

**Step 1: Write failing test** covering `to_wire`/`from_wire`/`from_exchange` for both brokers (e.g. Dhan `NSE→NSE_EQ`, Upstox `NFO→NSE_FO`).

**Step 2: Run → FAIL. Step 3: Implement** using exact tables from spec §5.2 / §6.2.

**Step 4: Run → PASS. Step 5: commit** `feat(brokers): add Dhan/Upstox segment mappers`.

---

## Task 6: Shared progressive-fallback resolver (spec §5.3 / §6.4) — core reimplementation

**Objective:** Encode the spec's multi-step progressive lookup + index fallback as a shared
helper, parameterized per broker, so v2 stays flat but behaves like the spec.

**Files:**
- Create: `v2/src/plugins/brokers/common/resolution.py` (`resolve_with_fallback`)
- Modify: `v2/src/plugins/brokers/dhan/adapters/instruments.py`, `v2/src/plugins/brokers/upstox/adapters/instruments.py` (call the helper)
- Test: `v2/tests/unit/plugins/brokers/test_resolution_fallback.py`

**Design (DRY — one helper, two broker configs):**

```python
def resolve_with_fallback(
    *, symbol: str, exchange: str,
    resolver,                       # v2 InMemoryInstrumentResolver (alias-indexed)
    normalize_exchange,             # broker fn: exchange -> canonical
    index_fallback,                 # fn(symbol)-> Optional[BrokerWireRef] (hardcoded index)
    expected_segment: str | None = None,
) -> ResolvedInstrument | BrokerWireRef:
    sym = normalize_symbol(symbol)
    exch = normalize_exchange(exchange)
    # 1. direct (EXCHANGE:SYMBOL)
    # 2. stripped
    # 3. CALL->CE / PUT->PE
    # 4. stripped option
    # 5. index fallback (exchange.INDEX)
    # 6. hardcoded index fallback via index_fallback()
```

Steps mirror spec §5.3 (Dhan 6-step) and §6.4 (Upstox 4-step). **Step 1: write failing
test** (resolve "NIFTY" on NSE → index fallback returns wire ref with security_id 13 for
Dhan / instrument_key for Upstox). **Step 2: run FAIL. Step 3: implement helper + wire
both adapters' `resolve`/`resolve_ref` to call it. Step 4: run PASS. Step 5: commit**
`feat(common): shared progressive resolution + index fallback`.

---

## Task 7: Wire fallback into gateway-facing resolver API

**Objective:** Expose `resolve(symbol, exchange)` / `resolve_ref(symbol, exchange, expected_segment)` on each broker's instrument adapter (Dhan/Upstox/Paper) using the helper from Task 6; keep `register_security`/`register_key` alias fan-out (already done) feeding the index.

**Files:**
- Modify: `v2/src/plugins/brokers/dhan/adapters/instruments.py`, `upstox/adapters/instruments.py`, `paper/adapters/instruments.py`
- Test: extend `test_resolution_fallback.py`

**Step 1: failing test** — `DhanInstrumentAdapter().resolve("NIFTY", "NSE")` returns `ResolvedInstrument` with `canonical_symbol="NIFTY 50"` (via index fallback).

**Step 2: run FAIL. Step 3: implement** thin wrappers delegating to `resolve_with_fallback`. **Step 4: run PASS. Step 5: commit** `feat(brokers): expose spec-signature resolve/resolve_ref`.

---

## Task 8: Full-suite regression + end-to-end parity probe

**Objective:** Confirm no regressions and spec compliance.

**Files:** none (verification only)
- Run `env -u PYTHONPATH .../venv/bin/python -m pytest tests/unit/plugins -q` → expect **all green** (baseline 449 passed before this plan; new tests add ~30).
- Optional live probe (gateway-only, per user mandate):
  `env -u PYTHONPATH PYTHONPATH=src .../venv/bin/python -m tradex.check_connection --broker dhan`
  then resolve `NIFTY`, `NIFTY50`, `BANKNIFTY`, `RELIANCE-EQ` (suffix strip), `NIFTY 26 JUN 25000 CE` (alias) through `gateway.extension(...)` / instrument adapter and assert non-None wire refs.

---

## Risks / Tradeoffs / Open Questions

- **Scope vs v2 flatness:** The spec describes legacy 4-layer DTOs (`DhanInstrument`, `UpstoxInstrumentDefinition`, triple/quintuple indexes). Porting those verbatim contradicts v2's flatter design — this plan reimplements the *behavior* (fallback, preference, index fallback) via a shared helper instead of the DTOs. **Confirm with user** if they want the full legacy DTO port instead.
- **Preference rules** (EQUITY>FUTURE>OPTION, equity-share>bond, nearest-active-future): the spec's `SymbolResolver` applies these during bulk load. v2's alias fan-out stores all forms pointing to one wire — preference is implicitly "last-write-wins". Task 6's helper should encode the index-fallback guard (reject index when `expected_segment` is derivative); full preference at load-time is lower priority (note in code).
- **`Instrument` dataclass** (v2) vs `InstrumentRecord` (spec §1.5): v2 keeps `Instrument`; do NOT add `InstrumentRecord` unless needed by adapters.
- **`config/indices.py` vs `common/index_map.py`:** plan extends `index_map.py` in place (v2 has no `config/` dir). No new `config/` package.

## Verification (end of plan)

```bash
cd /Users/apple/Downloads/Trade_XV2/v2 && env -u PYTHONPATH /Users/apple/Downloads/Trade_XV2/venv/bin/python -m pytest tests/unit/plugins -q
```
Expected: all green (449 prior + ~30 new). Then optional live probe above.
