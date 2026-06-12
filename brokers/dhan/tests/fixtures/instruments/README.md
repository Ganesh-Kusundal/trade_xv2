# Dhan Instrument Master — test fixture

This directory contains a **real, downloaded copy** of Dhan's daily
instrument master CSV. It is the ground truth that the
`brokers/dhan/instrument_service.py` tests pin themselves to.

## File

| Field         | Value |
|---------------|-------|
| File          | `api-scrip-master-LATEST.csv` |
| Downloaded    | 2026-06-11 |
| Size          | 1.79 MB |
| SHA-256       | `78782d25ea12143ee190421fe936b2b2d7b75bad1e846446338289aacaeae8b3` |
| Rows          | 17,628 data rows + 1 header = 17,629 lines |
| Source URL    | `https://images.dhan.co/api-data/api-scrip-master.csv` |

## How to regenerate

```bash
python -c "import urllib.request; urllib.request.urlretrieve('https://images.dhan.co/api-data/api-scrip-master.csv', 'brokers/dhan/tests/fixtures/instruments/api-scrip-master-LATEST.csv')"
```

If the network is offline, the test suite will still pass against the
committed copy.  The fixture only needs to be refreshed when Dhan
publishes a new daily master **and** the test outcomes change.

## Truncation

The original Dhan file is ~29 MB / 231 k rows.  Plan §7 M1 says:
*“If the file is too large for the repo (>10MB), keep only the first
5000 rows + the full F&O/options universe and document the truncation.”*

A literal application of that rule would have lost most NSE/BSE equity
rows and every index.  We therefore produced a **stratified sample**
that keeps the resolution contract end-to-end:

| Segment kept                | Rows  | Selection rule                                        |
|-----------------------------|-------|-------------------------------------------------------|
| `NSE::E` (NSE equity)       | 7 307 | all rows with SID ≤ 50 000 (the well-known large-caps) |
| `BSE::E` (BSE equity)       | 5 958 | all rows with SID ≤ 600 000                            |
| `NSE::I` (NSE indices)      | 119   | all rows kept                                         |
| `BSE::I` (BSE indices)      | 75    | all rows kept                                         |
| `NSE::D` (NSE F&O)          | 1-in-50 sample of 93 542 → 1 871 | options & futures universe |
| `BSE::D` (BSE F&O)          | 1-in-50 sample of 42 381 → 848   | SENSEX options             |
| `NSE::M` (MCX-on-NSE)       | 1-in-50 sample of 32 506 → 651   | commodity options          |
| `MCX::M` (MCX commodity)    | 1-in-50 sample of 15 703 → 315   | CRUDEOIL, GOLDM futures    |
| `NSE::C` (NSE currency)     | 1-in-50 sample of 11 429 → 229   | USDINR                     |
| `BSE::C` (BSE currency)     | 1-in-50 sample of 12 733 → 255   | BSE USDINR                 |

Total: 17 628 data rows.  The fixture is **1.79 MB** (well under the
10 MB cap from plan R1).

The truncation is **de-duplicated by `(exch, segment, security_id)`**,
the true uniqueness key in the Dhan master (the same numeric SID can
legitimately appear in different `(exch, segment)` pairs — e.g. SID
2885 is RELIANCE on NSE equity and a different F&O row in a different
segment).

## What is NOT in the fixture

* Penny stocks with NSE SID > 50 000 — most are not in the seed
  table and are not used by any of the resolution smoke tests.
* BSE-only penny stocks with BSE SID > 600 000.
* Most expiring options/futures — the 1-in-50 stride drops 49 rows
  out of every 50 in the F&O universe.  Tests asserting exact
  (strike, expiry) tuples for non-`NIFTY`/`BANKNIFTY` underlyings must
  regenerate the fixture.

## Verification

The `brokers/dhan/tests/fixtures/conftest.py` `instrument_service`
fixture points at this file and the
`brokers/dhan/tests/unit/test_instrument_service.py` smoke tests verify
that the canonical seed instruments resolve correctly:

| Symbol     | Exchange | Expected SID |
|------------|----------|--------------|
| RELIANCE   | NSE      | 2885         |
| TCS        | NSE      | 11536        |
| INFY       | NSE      | 1594         |
| HDFCBANK   | NSE      | 1333         |
| SBIN       | NSE      | 3045         |
| NIFTY      | IDX_I    | 13           |
| BANKNIFTY  | IDX_I    | 25           |
| FINNIFTY   | IDX_I    | 27           |
| SENSEX     | IDX_I    | 51           |
| MIDCPNIFTY | IDX_I    | 442          |
| RELIANCE   | BSE      | 500325       |
| WIPRO      | NSE      | 3787         |
| AXISBANK   | NSE      | 5900         |
| MARUTI     | NSE      | 10999        |
| TITAN      | NSE      | 3506         |

## Performance note

The Dhan catalog's `replace_all` has an O(n²) hot loop
(`_append_to` does a linear scan on every insert).  The 17 628-row
fixture loads in ~10 s on a developer laptop — acceptable for a
module-scoped pytest fixture, but if it becomes a CI bottleneck,
M2 should swap the `replace_all` body for a single
`collections.defaultdict(list)` pass (the plan's R1 mitigation).
