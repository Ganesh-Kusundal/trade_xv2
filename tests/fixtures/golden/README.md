# Golden Datasets

Golden datasets are versioned reference fixtures used to validate broker resolution, tick parsing, and symbol mapping against known-correct expected values. They are the "unit tests of reality" — when a broker plugin resolves `RELIANCE` on `NSE`, we know the answer it *should* give.

---

## Directory Structure

```
tests/fixtures/golden/
├── README.md                   ← this file
├── manifest.yaml               ← registry of all golden datasets
├── dhan_bus_ticks.json         ← Dhan market-feed quote parsing golden
├── upstox_bus_ticks.json       ← Upstox V3 tick frame parsing golden
└── ../ledger/
    └── shadow_parity_24h.json  ← 24h fill session for shadow parity
```

The canonical instrument-resolution golden dataset lives at:

```
src/brokers/certification/golden_dataset.json
```

---

## How It Works

### 1. Instrument Resolution Golden (`golden_dataset.json`)

Validates that each broker resolves symbols to the correct exchange, tick size, lot size, and instrument ID.

**Loaded by:** `brokers.certification.golden.load_golden_cases()`

Each case specifies:

```json
{
  "symbol": "RELIANCE",
  "exchange": "NSE",
  "expected_exchange": "NSE",
  "expected_tick_size": "0.05",
  "expected_lot_size": 1,
  "expected_instrument_id": "NSE:RELIANCE",
  "expected_security_id": null,
  "asset": "equity"
}
```

**Fields:**

| Field | Required | Description |
|-------|----------|-------------|
| `symbol` | Yes | Trading symbol to resolve |
| `exchange` | Yes | Exchange to resolve against (NSE, BSE, NFO, MCX) |
| `expected_exchange` | Yes | Expected resolved exchange |
| `expected_tick_size` | No | Expected minimum price movement (string) |
| `expected_lot_size` | No | Expected lot size (int) |
| `expected_instrument_id` | No | Expected canonical instrument ID string (e.g. `NSE:RELIANCE`) |
| `expected_security_id` | No | Broker-specific security ID (live only, filled on symbol-master refresh) |
| `asset` | No | Asset kind: `equity` (default), `index`, `future`, `option`, `currency`, `commodity` |

### 2. Tick-Frame Golden (Bus Certifications)

Validate that raw broker WebSocket frames are correctly parsed into domain `TICK` events.

**Format:**

```json
{
  "version": "1.0",
  "description": "Description of what this dataset tests",
  "cases": [
    {
      "id": "unique_case_id",
      "quote": { ... },
      "expected": {
        "event_type": "TICK",
        "symbol": "RELIANCE",
        "ltp": "2450.5",
        "source": "DhanMarketFeed"
      }
    }
  ]
}
```

**Fields per case:**

| Field | Required | Description |
|-------|----------|-------------|
| `id` | Yes | Unique case identifier |
| `quote` / `payload` | Yes | Raw input data (format depends on broker) |
| `frame_type` | No | WebSocket frame type (e.g. `ltpc`, `full`) |
| `expected` | Yes | Expected parsed output values |
| `expected.dropped` | No | If `true`, case expects the tick to be dropped (e.g. zero LTP) |

---

## Schema Validation

Golden datasets are validated by:

- **`brokers.certification.golden`** — `GoldenCase` dataclass and `_check_case()` validates instrument resolution against expected values
- **`brokers.certification.schema_v2`** — `validate_verify_report()` / `validate_certification_report()` validates certification report JSON against schema v2 (ADR-018)
- **`brokers.certification.mapping`** — `MappingReport` validates round-trip symbol → instrument → ID → symbol for the default asset/exchange matrix

---

## Creating New Golden Datasets

### Adding an instrument resolution case

1. Open `src/brokers/certification/golden_dataset.json`
2. Add a new entry to the `cases` array:

```json
{
  "symbol": "SBIN",
  "exchange": "NSE",
  "expected_exchange": "NSE",
  "expected_tick_size": "0.05",
  "expected_lot_size": 1,
  "expected_instrument_id": "NSE:SBIN",
  "asset": "equity"
}
```

3. Update the `version` and `updated` fields at the top of the file
4. Run certification to verify:

```bash
broker certify --broker paper
```

### Adding a tick-frame golden dataset

1. Create a new JSON file in `tests/fixtures/golden/` following the format above
2. Register it in `tests/fixtures/golden/manifest.yaml`:

```yaml
datasets:
  - id: my_new_dataset
    path: my_new_dataset.json
    provenance: "description of data source"
    use: [unit, certification]
    test: tests/unit/path/to/test_file.py
```

3. Write the corresponding test that loads and validates against the golden data

### Adding a golden case for a different asset class

The `asset` field controls which `BrokerSession` method is called during validation:

| `asset` value | Resolution method |
|---------------|-------------------|
| `equity` | `session.stock(symbol, exchange=...)` |
| `index` | `session.index(symbol, exchange=...)` |
| `future` | `session.future(symbol, expiry=..., exchange=...)` |
| `option` | `session.option(symbol, strike=..., right=..., expiry=..., exchange=...)` |
| `currency` | `session.currency(symbol, exchange=...)` |
| `commodity` | `session.commodity(symbol, expiry=..., exchange=...)` |

For derivatives, `expected_tick_size` and `expected_lot_size` are broker-specific and may vary.

---

## Versioning Strategy

### Version fields

Every golden dataset JSON file carries a top-level `version` string and an `updated` date:

```json
{
  "version": "1.1",
  "updated": "2026-07-11",
  ...
}
```

### Semver rules

| Change type | Version bump | Example |
|-------------|-------------|---------|
| Add new case | Minor | `1.0` → `1.1` |
| Remove case | Major | `1.1` → `2.0` |
| Fix expected value | Patch | `1.0` → `1.1` (treat as minor since it's data) |
| Change schema | Major | `1.x` → `2.0` |
| Broker format change | Major | `1.x` → `2.0` |

### Manifest versioning

`manifest.yaml` carries its own `version` field (currently `"1.0"`). Bump when:

- Adding or removing a dataset entry
- Changing provenance or test path
- Changing the `use` categories

### Freshness validation

Golden data may become stale as market data changes (tick sizes, lot sizes, instrument IDs). Mitigations:

1. **`expected_instrument_id`** uses the canonical `EXCHANGE:SYMBOL` format which is stable — it does not change with market data
2. **`expected_tick_size`** and **`expected_lot_size`** are exchange-level constants for equities — only change if exchange规则 changes
3. **`expected_security_id`** is live-broker only and optional — the paper broker always uses the canonical instrument ID
4. **Tick-frame golden data** uses synthetic values that never change — they test parsing logic, not market data

### CI integration

Golden datasets are exercised by:

- `tests/unit/brokers/certification/test_certification_paper.py` — instrument resolution golden
- `tests/unit/brokers/dhan/test_dhan_bus_golden.py` — Dhan tick parsing golden
- `tests/unit/brokers/upstox/test_upstox_bus_golden.py` — Upstox tick parsing golden
- `tests/architecture/test_shadow_parity_gate.py` — ledger shadow parity golden

Run all golden tests:

```bash
pytest tests/ -k golden -v
```

---

*Generated for Phase 4 — Task D4.4 of the Transformation Roadmap.*
