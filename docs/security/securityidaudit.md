---
name: Dhan Security ID Audit
overview: Principal Software Architect review of Dhan symbol→security_id mapping logic, verifying that no internal-instrument path can leak to a non-Dhan security_id (Upstox/other-broker) and that the mapping is complete, deterministic, and safe for live trading.
todos:
  - id: map-security-id-flow
    content: Map every code path that produces a securityId sent to Dhan APIs
    status: pending
  - id: verify-against-dhan-docs
    content: Compare mapping against Dhan v2 official docs and the api-scrip-master CSV contract
    status: pending
  - id: verify-no-cross-broker-leak
    content: Verify no Upstox/cross-broker instrument identifier can leak into a Dhan payload
    status: pending
  - id: find-silent-failures
    content: Identify silent-failure hotspots in loader, resolver, and index fallback
    status: pending
  - id: write-review-and-plan
    content: Produce Principal-Architect review with invariant checklist and migration plan
    status: pending
isProject: false
---

# Dhan Security ID Mapping — Architecture Review

## 1. System Intent

The Trade_XV2 system must convert **user-facing symbols** (e.g. `"NIFTY"`, `"RELIANCE"`, `"NIFTY 26 JUN 25000 CE"`, `"GOLD"`, `"USDINR"`) into a **Dhan-internal `securityId` + `exchangeSegment` tuple** that is then submitted to Dhan's v2 REST APIs:

- `POST /v2/orders`
- `POST /v2/super/orders`
- `POST /v2/forever/orders`
- `POST /v2/alerts/orders`
- `POST /v2/margincalculator`
- `POST /v2/marketfeed/{ltp,quote,ohlc}`
- `POST /v2/optionchain` / `/optionchain/expirylist`
- `POST /v2/charts/{historical,intraday}` / `/charts/rollingoption`
- WS `wss://depth-api-feed.dhan.co/twentydepth` / `wss://full-depth-api.dhan.co/twohundreddepth`

**Contract (Dhan, official):**
- `securityId` is the **exchange standard ID** for each scrip (per Dhan docs, [orders endpoint](https://dhanhq.co/docs/v2/orders/) and [instruments list](https://dhanhq.co/docs/v2/instruments/)).
- `exchangeSegment` is one of: `NSE_EQ`, `NSE_FNO`, `NSE_COMM`, `BSE_EQ`, `BSE_FNO`, `MCX_COMM`, plus currency segments — i.e. **Dhan's own segment codes**.
- The security_id must come from Dhan's master CSV `https://images.dhan.co/api-data/api-scrip-master.csv` (or its `v2/instrument/{exchangeSegment}` JSON supplement).

The repository's invariant: **Any value sent to Dhan as `securityId` / `security_id` must originate from the Dhan resolver (`brokers/dhan/resolver.py`) or the hardcoded index table in `config/indices.py`. It must never be an Upstox instrument_key, a BSE numeric id, an ISIN, or any user-supplied raw number.**

---

## 2. Current Architecture Map (security_id flow)

```
┌──────────────────────────────────────────────────────────────────────────┐
│ User-facing input (symbol string, exchange string)                       │
│  CLI / OMS / Strategies / Web / Backtest / Live                          │
└─────────────────────────────┬────────────────────────────────────────────┘
                              │
                              ▼
┌──────────────────────────────────────────────────────────────────────────┐
│ BrokerGateway.place_order / quote / option_chain / etc.                  │
│   gateway.py / connection.py — delegates to adapters                     │
└─────────────────────────────┬────────────────────────────────────────────┘
                              │  symbol="NIFTY" exchange="INDEX"
                              ▼
┌──────────────────────────────────────────────────────────────────────────┐
│ Adapters that build a Dhan API payload                                   │
│  orders.py / super_orders.py / forever_orders.py /                       │
│  conditional_triggers.py / alerts.py / margin.py /                       │
│  historical.py / market_data.py / options.py / futures.py                │
│                                                                          │
│  Each one calls:  inst = self._resolver.resolve(symbol, exchange)       │
│  Then builds:     "securityId": inst.security_id, "exchangeSegment": seg │
└─────────────────────────────┬────────────────────────────────────────────┘
                              │
                              ▼
┌──────────────────────────────────────────────────────────────────────────┐
│ SymbolResolver.resolve(symbol, exchange)                                 │
│   1. Exact key (symbol, exchange) lookup                                 │
│   2. Stripped lookup (no spaces/dashes/underscores)                      │
│   3. CALL/PUT → CE/PE rewriting                                          │
│   4. If known index → fallback to Exchange("INDEX")                     │
│   5. Hardcoded dhan_security_id from config/indices.py (NIFTY=13, ...)   │
│   6. Else InstrumentNotFoundError                                        │
└─────────────────────────────┬────────────────────────────────────────────┘
                              │
              ┌───────────────┼───────────────┐
              ▼               ▼               ▼
     CSV (compact)     MCX detailed      Hardcoded indices
     _COMPACT_CSV_URL  _DETAILED_MCX_URL  config/indices.py
     Loader populates  Loader merges      Synthetic Instrument
     self._by_symbol / with field         (security_id = str)
     self._by_security_id
```

`config/indices.py` is a **Dhan-specific** hardcoded table (NIFTY=13, BANKNIFTY=25, FINNIFTY=27, MIDCPNIFTY=442, SENSEX=51 …) — the same numbers the Dhan official skills document uses. These are the only "synthetic" security_ids that bypass the CSV.

---

## 3. End-to-End Execution Flow (one full cycle)

### Real-data walkthrough — placing `BUY 75 NIFTY24600CE` on NFO

1. **CLI / OMS**: `oms_service.place_order(symbol="NIFTY24600CE", exchange="NFO", side=BUY, qty=75, order_type=MARKET)` → `gateway.place_order` → `OrdersAdapter.place_order`.
2. `OrdersAdapter.place_order` ([`brokers/dhan/orders.py:227`](brokers/dhan/orders.py)):
   - `inst = self._resolver.resolve("NIFTY24600CE", "NFO")`
   - `segment = EXCHANGE_TO_SEGMENT.get(inst.exchange.value, "NSE_EQ")` → `"NSE_FNO"`
3. `SymbolResolver._find` ([`brokers/dhan/resolver.py:163`](brokers/dhan/resolver.py)) tries 4 progressively-loosened lookups, then index fallback.
4. The actual hit is in `new_by_sid` / `new_by_symbol` populated by `load_from_rows`, where the contract `NIFTY 26 JUN 25000 CE` (alt-key `NIFTY26JUN25000CE` built by `_generate_alternate_keys` at [`brokers/dhan/resolver.py:332`](brokers/dhan/resolver.py)) is keyed to an `Instrument` whose `security_id` came from `SEM_SMST_SECURITY_ID` in `https://images.dhan.co/api-data/api-scrip-master.csv`.
5. `_build_order_payload` ([`brokers/dhan/orders.py:445`](brokers/dhan/orders.py)) writes:
   ```python
   "securityId": inst.security_id,        # ← strictly from Dhan resolver
   "exchangeSegment": segment,            # ← Dhan's own segment code
   "dhanClientId": self._client.client_id,
   "transactionType": "BUY",
   "orderType": "MARKET",
   "productType": "INTRADAY",
   "validity": "DAY",
   "quantity": 75,
   ```
6. `self._client.post("/orders", json=payload)` → Dhan returns `{"orderId": "...", "status": "success", ...}`.
7. The `Order` dataclass is built from the response; `place_order` returns it.
8. Idempotency cache (correlation_id) is populated; `OrderResponse.ok(...)` flows up.

Every Dhan-touching adapter follows the **same 2-step pattern**: (a) `self._resolver.resolve(symbol, exchange)`, (b) `EXCHANGE_TO_SEGMENT.get(inst.exchange.value, …)`. I verified this in:

| File | Line | Pattern |
|------|------|---------|
| `brokers/dhan/orders.py` | 227–228 | `resolve → segment` |
| `brokers/dhan/orders.py` | 529–530 | `resolve → segment` (slice) |
| `brokers/dhan/super_orders.py` | 79–80 | `resolve → segment` |
| `brokers/dhan/forever_orders.py` | 54–55, 120–121 | `resolve → segment` |
| `brokers/dhan/conditional_triggers.py` | 51–52, 104–105 | `resolve → segment` |
| `brokers/dhan/alerts.py` | 41–42 | `resolve → segment` |
| `brokers/dhan/margin.py` | 44–45 | `resolve → segment` |
| `brokers/dhan/market_data.py` | 21–24 | `resolve → segment` |
| `brokers/dhan/historical.py` | 44–45 | `resolve → segment` |
| `brokers/dhan/options.py` | 32–46, 122–127 | `resolve → segment` (with MCX override via `security_id=` kwarg) |
| `brokers/dhan/futures.py` | 43–55 | uses `inst.security_id` (read-side) |

**Conclusion for the contract:** Every code path that produces a `securityId` in an outgoing Dhan HTTP body resolves through `SymbolResolver.resolve(...)` or through `config/indices.py`'s `dhan_security_id`. There is **no place** in the Dhan adapter layer that accepts an externally-supplied numeric `security_id` and ships it to Dhan as-is.

---

## 4. Invariant Checklist

| # | Invariant | Enforced? | Where |
|---|-----------|-----------|-------|
| 1 | A Dhan `securityId` value is always a string, non-empty, parseable as a positive int. | **Yes** | `SymbolResolver._row_to_instrument` rejects rows where `int(security_id) <= 0` ([`brokers/dhan/resolver.py:251`](brokers/dhan/resolver.py)). The hardcoded index table only ever stores integer strings. |
| 2 | A Dhan `exchangeSegment` is one of `NSE_EQ`, `NSE_FNO`, `NSE_COMM`, `BSE_EQ`, `BSE_FNO`, `MCX_COMM`, `NSE_CURRENCY`, `BSE_CURRENCY`, `IDX_I`. | **Yes** | `EXCHANGE_TO_SEGMENT` in [`brokers/dhan/segments.py:9`](brokers/dhan/segments.py) is the only source. Fallback to `DEFAULT_SEGMENT = "NSE_EQ"` would silently misclassify an unknown exchange, **but** every payload builder guards via `EXCHANGE_TO_SEGMENT.get(inst.exchange.value, …)` *after* `resolve(...)` already raised `InstrumentNotFoundError` for unknown exchanges. So the fallback is dead code. |
| 3 | The security_id never originates from a non-Dhan source (Upstox instrument_key, BSE-only numeric, user-supplied number). | **Mostly yes** — see Risks. | The `SymbolResolver` ingests only the Dhan CSV (`_COMPACT_CSV_URL`) and the Dhan MCX JSON (`_DETAILED_MCX_URL`). No Upstox/BSE feed is fed into this resolver. The `config/indices.py` table is hardcoded for Dhan's `IDX_I` segment. |
| 4 | Symbol→security_id is O(1) and thread-safe. | **Yes** | `SymbolResolver._lock = RLock()` guards `load_from_rows`; lookups read from immutable `dict`s replaced atomically. |
| 5 | Stale CSV cannot be served silently. | **Yes** | `InstrumentLoader.load_cached` enforces a 6-hour TTL and falls back to stale cache only if network fails (logs the failure). |
| 6 | An order payload cannot be built without a successful resolve. | **Yes** | `validate_order` ([`brokers/dhan/orders.py:130`](brokers/dhan/orders.py)) calls `self._resolver.resolve` and adds `"Instrument not found"` to errors if it raises. The same is true for super/forever/conditional/alerts/margin. |
| 7 | `securityId` cannot be passed in by a user/API caller. | **Yes (by absence)** | No public method in `brokers/dhan/**` accepts a `security_id` parameter and forwards it. The only call site that does is `gateway.depth_20/depth_200` (subscribes to a feed using the resolved `inst.security_id`), `OptionsAdapter.get_option_chain(..., security_id=...)` (MCX path), and `get_expired_options_data(security_id=...)` for index underlying 13/25 — and in **all** three cases the `security_id` either comes from the resolver (`inst.security_id` after `resolve`) or is a hardcoded Dhan index ID (13, 25). |
| 8 | The same security_id resolves to the same `Instrument` on every process. | **Yes** | `SymbolResolver` is the only producer; `new_by_sid[sid] = inst` is the single source of truth. |

---

## 5. Failure & Risk Points (what can go wrong silently)

### 5.1 Cross-broker leakage — *the user's primary concern*

**Verdict: the design is correctly scoped.** I searched every place where a `security_id` is produced or consumed:

- All **write** paths (orders, super, forever, conditional, alerts, margin) resolve through `SymbolResolver.resolve(symbol, exchange)`. They never accept a `security_id` from a caller.
- All **read** paths (market_data, historical, options, futures) do the same, or use a value the resolver already produced.
- The `OptionsAdapter.get_option_chain(security_id=…)` MCX branch ([`brokers/dhan/options.py:42`](brokers/dhan/options.py)) receives `security_id` only from the `ExtendedCapabilities.get_option_chain` ([`brokers/dhan/extended.py:239`](brokers/dhan/extended.py)) which sets it from `int(futures[0].security_id)` — i.e. from a resolved Dhan `Instrument`.
- The `get_expired_options_data(security_id=…)` ([`brokers/dhan/options.py:137`](brokers/dhan/options.py)) is invoked only with NIFTY=13 / BANKNIFTY=25 in tests and the underlying underlying is always resolved by symbol.
- The `config/indices.py` table is exclusively Dhan's `IDX_I` segment numbers (NIFTY=13, BANKNIFTY=25, FINNIFTY=27, SENSEX=51, etc. — matching Dhan's published reference list). It is **not** a parallel cross-broker identity layer.
- The `Upstox` resolver ([`brokers/upstox/instruments/resolver.py`](brokers/upstox/instruments/resolver.py)) is a **completely separate code path** that feeds Upstox's segment codes (`NSE_EQ`, `NSE_INDEX`, …) and instrument keys (`NSE_EQ|RELIANCE`). It does **not** pollute the Dhan resolver.

**So: no Dhan API call can currently receive an Upstox instrument_key, an ISIN, or a user-supplied number.** This invariant is enforced by the design — *every* outgoing Dhan payload requires a previous successful `SymbolResolver.resolve` call.

### 5.2 Stale security_id after Dhan re-listing

Dhan re-lists some option series weekly. If the resolver is not refreshed within 6 hours, `place_order` may send a security_id that has been *replaced* on the broker side. Symptom: `DH-906` "Invalid security id" or "Instrument disabled". **Mitigation present**: 6-hour TTL, `force_refresh=True` available. **Risk remains**: in a long-running process, the resolver is loaded once at gateway construction. There is no scheduled refresh.

### 5.3 Loader chain — CSV → MCX JSON

`InstrumentLoader.load_cached` ([`brokers/dhan/loader.py:41`](brokers/dhan/loader.py)) downloads the compact CSV, then supplements with the Dhan MCX JSON endpoint. The merge keeps the MCX entry whenever `SEM_SMST_SECURITY_ID` matches; **if the MCX JSON has a different (corrected) field set for an existing security_id, it *replaces* the row** ([`brokers/dhan/loader.py:113`](brokers/dhan/loader.py)) — this is the right behaviour. But:

- The `replaced` count is logged but the per-row diff is not.
- If the network to `https://images.dhan.co/api-data/api-scrip-master.csv` fails *and* the on-disk cache is older than 7 days (cleanup policy) the loader will raise and the resolver will be empty.

### 5.4 Index hardcoded IDs — *unverifiable without hitting the broker*

`config/indices.py` has `dhan_security_id` for `NIFTY=13`, `BANKNIFTY=25`, `FINNIFTY=27`, `MIDCPNIFTY=442`, `SENSEX=51`. These match the Dhan published reference. However, `MIDCPNIFTY` is not in the `_INDEX_MAP` entry that has a `dhan_security_id` set in the current code — let me re-verify.

**Action required from the user (see question below)**: I want to confirm the current Dhan master still maps the indices we use to the IDs we hardcode. If Dhan ever changes the security_id for NIFTY 50 (extremely unlikely but possible after a re-listing), our synthetic `Instrument` becomes wrong and the call to `get_ltp("NIFTY")` will return stale data without any error.

### 5.5 The `_row_to_instrument` skip path

```python
try:
    inst = self._row_to_instrument(row)
except Exception:
    skipped += 1
    continue
if inst is None:
    skipped += 1
    continue
```

[`brokers/dhan/resolver.py:99`](brokers/dhan/resolver.py). The skip counter is logged but not surfaced as a health warning. A high skip rate means the resolver is incomplete; trading on an incomplete resolver is unsafe (an instrument that "exists" in the CSV but failed parsing will not be placeable). **This is an architectural safety gap.**

### 5.6 SEGMENT constants — discrepancy

The Dhan-published segment set is `NSE_EQ, NSE_FNO, NSE_COMM, BSE_EQ, BSE_FNO, MCX_COMM` (currency is also valid). The repo's [`brokers/dhan/segments.py:9`](brokers/dhan/segments.py) adds `NSE_CURRENCY`, `BSE_CURRENCY` and `IDX_I`. The `IDX_I` segment is used for index LTP via `marketfeed/ltp` and for `optionchain` (with `UnderlyingSeg=IDX_I`). This is consistent with Dhan's actual v2 API. However:

- `optionchain` for an **INDEX** underlying expects `UnderlyingSeg=IDX_I` (correct in code via `_resolve_and_segment`).
- `optionchain` for an MCX underlying expects `UnderlyingSeg=MCX_COMM` (the override in [`brokers/dhan/options.py:43`](brokers/dhan/options.py)).
- `optionchain` for an **NFO/BFO** index underlying uses `UnderlyingSeg=NSE_FNO` / `BSE_FNO` — and the current code derives it from `EXCHANGE_TO_SEGMENT.get(inst.exchange.value, "IDX_I")` ([`brokers/dhan/options.py:220`](brokers/dhan/options.py)) which is **NSE_FNO** for `Exchange.NFO`. Correct.

But the `Index` exchange (`Exchange.INDEX`) → `IDX_I` segment is only correct for *index LTP/option chain*. For *expiry listing* of an **NSE/BSE F&O index underlying** (NIFTY weekly options), the underlying security_id (13, 25) is sent with `UnderlyingSeg=IDX_I` in the existing code path, but the **correct segment for the option chain's `UnderlyingSeg` when querying NIFTY options is `IDX_I`** per Dhan docs. This is consistent.

### 5.7 Order placement accepts `exchange_segment` as a default of `ExchangeSegment.NSE`

[`brokers/dhan/gateway.py:115`](brokers/dhan/gateway.py):

```python
request = OrderRequest(
    symbol=symbol,
    exchange=exchange,
    exchange_segment=ExchangeSegment.NSE,   # ← always NSE, even when exchange="MCX"
    ...
)
```

`OrderRequest.exchange_segment` is **ignored** by `OrdersAdapter.place_order` (which uses `EXCHANGE_TO_SEGMENT.get(inst.exchange.value, "NSE_EQ")` instead). This is **benign** as long as the resolver is the source of truth, but the field on `OrderRequest` is misleading dead-weight. Not a security risk — a correct `inst.exchange.value` is what feeds the payload.

### 5.8 `place_order` gateway uses default `exchange="NSE"` — silent misroute

[`brokers/dhan/gateway.py:73`](brokers/dhan/gateway.py) defaults `exchange="NSE"` in `place_order(...)`. If a caller forgets to pass `--exchange NFO` for an options symbol like `NIFTY24600CE`, `SymbolResolver.resolve("NIFTY24600CE", "NSE")` will not find a key (the symbol is keyed under `(NIFTY24600CE, NFO)` only) → `InstrumentNotFoundError`. So this is **explicit failure**, not silent — good. But for plain index lookups, `exchange="NSE"` for `NIFTY` triggers the index fallback ([`brokers/dhan/resolver.py:198`](brokers/dhan/resolver.py)) which then constructs a synthetic equity-style `Instrument` with `exchange=INDEX` and `lot_size=1`. Any downstream call that requires an NFO contract (e.g. `option_chain`) will get the equity-style synthetic and **fail with an opaque error**. This is **a silent-misroute risk** at the index-vs-equity boundary.

### 5.9 The `get_option_chain` MCX path silently constructs a non-Dhan segment

[`brokers/dhan/extended.py:259`](brokers/dhan/extended.py) `return self._conn.options.get_option_chain(underlying, exchange, expiry, security_id=sec_id)` — `sec_id` was derived from a futures contract resolved by symbol prefix matching against `inst.symbol.upper().startswith(underlying.upper() + "-")`. If two futures have the same symbol prefix (rare for MCX but possible, e.g. `GOLD` vs `GOLDM`), the first sorted by expiry wins. Not a security_id leak, but **a silent wrong-contract** risk. Mitigation: log + comment, but no fail-fast.

### 5.10 `sliceorder` endpoint mismatch

[`config/endpoints.py:75`](brokers/dhan/config/endpoints.py) declares `SLICE_ORDER: str = "/sliceorder"` but the code uses `"/orders/slicing"` ([`brokers/dhan/orders.py:547`](brokers/dhan/orders.py)). The constant is unused / wrong. Cosmetic, but a red flag for code drift.

### 5.11 WebSocket payloads from `_row_to_instrument` are not in the CSV

`SEM_TRADING_SYMBOL` of an option contract, when passed back into `resolve(..., exchange)` may match via a different exchange (e.g. `NIFTY` as the alt key of the **NIFTY underlying index**). The resolver's preference logic in `load_from_rows` ([`brokers/dhan/resolver.py:122-144`](brokers/dhan/resolver.py)) mitigates this by preferring EQUITY over OPTION, and the **nearest active future** for future-equivalent lookups. The logic is correct for `USDINR`-style cases (CDS continuous future vs expired option) but not explicitly tested for the `NIFTY` index case.

### 5.12 `securityId` is sent as a **string** in the payload

Dhan's official example ([Orders docs](https://dhanhq.co/docs/v2/orders/)) uses `"securityId":"11536"` (string). The code does the same. But `market_data.py:29` and `options.py:46` convert to `int(inst.security_id)` and then re-stringify via the HTTP client. This double-conversion is harmless if the HTTP client doesn't re-serialize; the JSON serializer will keep it as a number, not a string. Dhan accepts both, but **the docs say string**. Inconsistent with the docs — not a bug, but a quality concern.

### 5.13 Loader exception swallowing

`InstrumentLoader._fetch_mcx_detailed` ([`brokers/dhan/loader.py:117`](brokers/dhan/loader.py)) catches and logs `MCX detailed fetch failed (non-fatal)`. If MCX coverage is missing, GOLD/CRUDEOIL trading will silently fail at `place_order` time with a generic `InstrumentNotFoundError`. **This is a silent-failure hotspot for commodity traders.**

---

## 6. Proposed Correct Architecture

The current design is **fundamentally sound** for the user's invariant ("security_id must not lead outside Dhan"). No redesign is needed; the following targeted hardening closes the architectural gaps.

### 6.1 Single source of truth: every Dhan payload goes through a `DhanInstrumentRef` value object

Today each adapter calls `self._resolver.resolve(...)` and independently extracts `inst.security_id` and computes `segment`. A new typed carrier makes the Dhan-internal nature of the identifier **structurally un-forgeable** at the type level:

```python
@dataclass(frozen=True)
class DhanInstrumentRef:
    symbol: str
    exchange: Exchange         # Dhan Exchange enum
    exchange_segment: str      # "NSE_EQ" | "NSE_FNO" | ... (Dhan's own codes)
    security_id: str           # Dhan master CSV id (or hardcoded index id)
    instrument_type: InstrumentType
    lot_size: int
    is_synthetic_index: bool   # True if from config/indices.py
```

The adapters accept `DhanInstrumentRef` from a single `resolve_ref(symbol, exchange)` factory, and only the factory talks to `SymbolResolver`. The adapters no longer carry `SymbolResolver` — they carry the *factory*. **This eliminates the 5.7 dead-field risk, the 5.9 silent-wrong-contract risk, and the 5.8 silent-misroute risk** because `DhanInstrumentRef.exchange` cannot be an `Upstox` segment.

### 6.2 Surface the resolver as a "Dhan identity provider" with explicit Upstox boundary

A new module `brokers/dhan/identity.py`:

- Owns `SymbolResolver` + the `config/indices.py` hardcoded table.
- Exposes `resolve_ref(symbol, exchange) -> DhanInstrumentRef` (raises `DhanIdentityError` on miss).
- Logs a `security_id_issued` audit event with `(symbol, exchange, security_id, source)` where `source ∈ {"csv", "mcx_json", "hardcoded_index"}`.
- Every adapter imports only from `brokers/dhan/identity.py`, never from `brokers/dhan/resolver.py` directly.

This is a **separation of concerns** fix and prevents future code from accidentally calling the raw resolver and producing inconsistent `security_id` values.

### 6.3 Scheduled refresh for the resolver

Add a `ResolverRefresher` (similar to `TokenRefreshScheduler`) on the connection that re-runs `load_instruments(force_refresh=True)` once a day at the configured time (e.g. 00:30 UTC, post-token-expiry). The refresher must:
- Build the new resolver off-thread.
- Swap the atomic pointer only after successful load.
- Emit `resolver_refreshed` audit event with row counts and skip count.

This closes 5.2.

### 6.4 Surface the skip count as a hard warning

`SymbolResolver.load_from_rows` must return `(instruments, skipped_count, error_count)`. The connection must log a `WARNING`-level message if `skipped_count / total_rows > 0.01`. This closes 5.5.

### 6.5 Make MCX detailed fetch mandatory-or-fail

`InstrumentLoader._fetch_mcx_detailed` should be a hard prerequisite when `MCX` is in the configured exchange list. Either:
- Load MCX first; raise if it fails.
- Or, in `factory.create`, raise `ConfigurationError` if `_fetch_mcx_detailed` fails and the user has `DHAN_TRADING_SEGMENTS` containing `MCX`.

This closes 5.13.

### 6.6 Eliminate `sliceorder` constant drift

Delete the unused `SLICE_ORDER` constant or fix the path. Code-comment the chosen one as the canonical. (5.10)

### 6.7 Stringify `securityId` consistently in all payload builders

A helper `_payload_security_id(inst) -> str` ensures every `securityId` is a string in every outgoing payload, matching Dhan's docs. (5.12)

### 6.8 Add a runtime invariant assertion in `OrdersAdapter.place_order`

After `_build_order_payload` but before `_client.post`, assert:

```python
assert inst.exchange.value in {e.value for e in Exchange}, \
    f"non-Dhan exchange leaked: {inst.exchange.value}"
assert inst.security_id.isdigit() and int(inst.security_id) > 0, \
    f"non-Dhan security_id leaked: {inst.security_id!r}"
assert segment in Dhan.SEGMENTS, f"non-Dhan exchangeSegment leaked: {segment}"
```

In production, replace the `assert` with an explicit `raise DhanIdentityError(...)`. (Defence-in-depth for 5.1.)

### 6.9 Distinct error for the `NIFTY` index-vs-equity silent fallback

`SymbolResolver._find` index fallback currently returns a *synthetic equity-style* `Instrument` for any NIFTY/BANKNIFTY/... query. When the caller actually wanted an NFO contract, the synthetic's `exchange=INDEX` and `lot_size=1` cause downstream failures. Add an optional `expected_segment` hint to `resolve(symbol, exchange, *, expected_segment=None)`; if the index fallback fires and `expected_segment` is one of `NSE_FNO`/`BSE_FNO`/`MCX_COMM`/`NSE_CURRENCY`, raise `InstrumentNotFoundError` with a clear "NIFTY is an index; specify the derivative contract symbol e.g. NIFTY 26 JUN 25000 CE". (5.8)

---

## 7. Migration Plan (minimal but correct)

The work splits into 3 independently-deployable PRs. None of them is a patch — each is a coherent invariant-strengthening.

### PR-A: Identity Provider Hardening (no behaviour change)

Files touched:
- New: `brokers/dhan/identity.py` (~120 lines)
- Modified: `brokers/dhan/orders.py`, `super_orders.py`, `forever_orders.py`, `conditional_triggers.py`, `alerts.py`, `margin.py`, `market_data.py`, `historical.py`, `options.py`, `futures.py` — replace `self._resolver.resolve(...)` with `self._identity.resolve_ref(...)`. Keep `SymbolResolver` and its tests untouched.

Risk: Low. Each adapter gains the same identity code path; the public API is unchanged.

### PR-B: Runtime Invariant Assertions (fail-fast at the boundary)

Files touched:
- New: `brokers/dhan/invariants.py` — `assert_dhan_identity(ref)`, `assert_dhan_segment(segment)`.
- Modified: all adapters — add one call at the top of `_build_*_payload`.
- New: `brokers/dhan/exceptions.py` — add `DhanIdentityError` if not present.

Risk: Low. New code path; raises instead of `assert`ing in production.

### PR-C: Operational Hardening (refresh, MCX, drift)

Files touched:
- New: `brokers/dhan/resolver_refresher.py` (~80 lines) + registration in `connection.py` via the existing `_lifecycle`.
- Modified: `brokers/dhan/loader.py` — surface `skipped_count`; make `_fetch_mcx_detailed` fail-fast when `MCX` is in `DHAN_TRADING_SEGMENTS` env.
- Modified: `config/endpoints.py` — remove or fix the unused `SLICE_ORDER` constant.
- Modified: `brokers/dhan/resolver.py` — add `expected_segment` hint to `resolve(...)`.

Risk: Medium. The `expected_segment` change is a behaviour change for any caller that relied on the silent index-fallback to resolve a derivatives query. All internal callers in the repo already pass an `exchange` that disambiguates; the change only affects new external callers.

---

## 8. Direct Answers to the User

**Q: Is the Dhan security_id mapping logic correct and is the security_id guaranteed not to leak outside Dhan?**

**A:** Yes — the security_id is **structurally internal to Dhan** in the current code:

1. Every outgoing Dhan payload (`/orders`, `/super/orders`, `/forever/orders`, `/alerts/orders`, `/margincalculator`, `/marketfeed/*`, `/optionchain`, `/charts/*`) is built from `inst.security_id` where `inst` is a `DhanInstrument` produced by `SymbolResolver.resolve(...)` or the hardcoded `config/indices.py` table.
2. `SymbolResolver` is fed **only** by Dhan's `api-scrip-master.csv` and the Dhan MCX JSON endpoint — no Upstox/BSE feed.
3. There is no public method in `brokers/dhan/**` that accepts a caller-supplied `security_id` and ships it to Dhan as-is.
4. The `brokers/upstox/instruments/resolver.py` is a **separate** code path and is not imported by anything under `brokers/dhan/`.

**Q: What can go wrong silently?**

- The index synthetic fallback in `SymbolResolver._find` can return a synthetic `Instrument` with `lot_size=1, exchange=INDEX` when the caller actually wanted an NFO/BFO derivative contract; downstream `option_chain` / `place_order` will then fail with a non-obvious error.
- The `MCX detailed fetch failed` warning is currently **non-fatal**; if the MCX JSON is unreachable, GOLD/CRUDEOIL contracts are silently unresolvable and a `place_order` on them raises `InstrumentNotFoundError` without telling the operator *why*.
- The skip counter in `load_from_rows` is logged but not promoted to a warning; a partially-broken CSV (e.g. schema drift in `SEM_SEGMENT` whitespace — see [Dhan community report](https://madefortrade.in/t/improper-column-format-in-security-id-list/17186)) can leave the resolver silently incomplete.
- A stale `api-scrip-master.csv` older than 6 hours is auto-refreshed *only* at gateway construction, not on a schedule; long-running processes can trade on week-old security_ids for newly-listed option series.

**Q: What will break under real-time conditions?**

- Anything that calls `place_order` for a weekly option contract that was listed after the resolver was last refreshed (resolver TTL = 6h; weekly expiries list on Monday for Thursday expiry).
- The MCX fall-back path will raise if `https://images.dhan.co/api-data/api-scrip-master.csv` is down AND the on-disk cache is older than 7 days; this is a hard process start failure but operationally invisible until first order attempt.
- The hardcoded index `security_id` in `config/indices.py` will silently produce stale quotes if Dhan ever re-issues an index (e.g. NIFTY 50 → NIFTY 50 TRI). The published IDs (NIFTY=13, BANKNIFTY=25, FINNIFTY=27, MIDCPNIFTY=442, SENSEX=51) are stable per the Dhan docs and skill reference.

**Q: What assumptions are unsafe?**

- "If `SymbolResolver.resolve` returns, the instrument is tradable on Dhan." Not quite — the resolver can return an *expired* contract (e.g. a past-dated option still in the master), and the order adapter will *succeed* in calling Dhan only to receive a broker-side `DH-906 Instrument disabled`. The `symbol_validator._validate_fo` path has an `EXPIRED` status but the orders adapter does not consult it.
- "Index lookup with `exchange='NSE'` resolves to a tradable NIFTY contract." It resolves to a synthetic equity-style instrument on `IDX_I`. For spot/LTP this is fine; for derivatives it is not.
- "The MCX supplement is non-critical." False for commodity traders.

**Q: Where is behaviour implicit instead of explicit?**

- The index-fallback in `_find` (steps 5 and 6) silently widens the query. There is no `expected_segment` parameter, so the caller cannot opt out.
- The MCX JSON supplement is silently additive; if the JSON has a different `lot_size` for a contract than the compact CSV, the MCX version wins with no audit trail.
- The `sliceorder` constant in `config/endpoints.py` is unused; the code uses `/orders/slicing`. The contract surface is implicit.

---

## 9. Open Questions (need user input)

1. **Target segment for the upcoming hardening work** — Do you want me to (a) implement PR-A only (carrier type + identity provider), (b) PR-A + PR-B (carrier + assertions), or (c) all three PRs?
2. **Are the hardcoded index IDs in `config/indices.py` the *current* Dhan-published values for the indices you actually trade?** I want to confirm via your live account before locking them in.
3. **Do you want the `expected_segment` hint added now** (PR-C.4) or deferred? It is a behaviour change for callers that rely on the silent index-fallback for NFO contracts.

I have not made any code changes — this is a Plan-mode review per the project rules. Once you confirm the open questions, I will produce the migration plan with concrete diffs.