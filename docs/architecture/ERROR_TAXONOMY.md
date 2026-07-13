# ERROR_TAXONOMY.md — Error Hierarchy

> Canonical exception hierarchy. `domain.errors` and `domain.exceptions` are the root —
> infrastructure, application, and broker code classify errors through these types, never by
> importing broker packages directly (`src/brokers/exceptions/__init__.py` re-exports
> `domain.errors.BrokerError` rather than defining its own — see
> `docs/architecture/backlog.md` G-series notes on duplicate error hierarchies). This file is
> a reading index over the source modules below; if it disagrees with the code, the code wins.

---

## 1. Root

Source: `src/domain/exceptions.py`.

```
TradeXV2Error(Exception)          — root exception for all TradeXV2 errors
```

## 2. Broker / connectivity errors

Source: `src/domain/errors.py`.

```
TradeXV2Error
└── BrokerError                        base for all broker-communication errors
    ├── RetryableError                 transient — safe to retry
    │   └── NetworkError               connection reset / DNS / timeout
    ├── NonRetryableError              permanent — do not retry
    ├── RateLimitError                 429 / throttled
    ├── CircuitBreakerOpenError        breaker open for a named circuit
    ├── AuthenticationError            auth/authorization failure
    ├── InstrumentNotFoundError        requested instrument not found
    ├── OrderError                     order placement/modify/cancel error
    └── NotSupportedError              feature not supported by broker
        └── ExitAllError               kill-switch exit-all operation failed

TradeXV2Error
├── BrokerNotReadyError                gateway unavailable / not authenticated (carries BootstrapStatus)
├── NotConfiguredError                 domain object used without composition-root wiring
└── UnsupportedGatewayOperationError    gateway does not implement a contract method
    (also NotImplementedError)

BrokerDegradedError(BrokerError)       all brokers unavailable; system degraded (carries health_status)
```

`RetryableError` is also exposed as `TradeXV2RecoverableError` (alias used by the retry
framework / global exception handler).

## 3. Routing / quota / coordination errors

Source: `src/domain/errors.py` (merged from the former `tradex/runtime/errors.py`).

```
RuntimeError
├── BrokerUnavailableError             broker not registered or health not usable
├── RoutingError                       no eligible broker for a routing request
└── QuotaExhaustedError                API quota exhausted past the wait deadline

NotImplementedError
└── UnsupportedExtensionError          broker doesn't support a requested extension

ValueError
└── MergeConflictError                 irreconcilable overlap in historical data chunks
```

## 4. Connect / session errors (product surface)

Source: `src/domain/connect_errors.py`.

```
TradeXV2Error
└── ConnectError                       raised when tradex.connect() cannot return a usable Session
```

`ConnectError` carries a stable machine `code` for CLI/log classification. Canonical codes:
`OMS_REQUIRED`, `ORDERS_DISABLED`, `MISSING_ENV`, `AUTH_FAILED`, `UNKNOWN_BROKER`,
`UNKNOWN_MODE`, `GATEWAY_FAILED`, `ENG_011`.

## 5. Broker-package wrappers

Source: `src/brokers/exceptions/__init__.py` — re-exports `domain.errors.BrokerError` (not a
separate definition; `tests/architecture/test_no_duplicate_error_hierarchies.py` guards this)
and adds two broker-scoped subclasses where the domain layer doesn't already cover the case:

```
BrokerError (== domain.errors.BrokerError)
├── BrokerNotAvailable                 requested broker plugin not registered/available
└── CapabilityNotSupported             instrument/broker lacks a requested capability
```

## 6. Risk-denial (not an exception — an event)

Risk denials (`RISK_REJECTED`) are **not** raised as exceptions on the hot order-placement
path — see `FLOWS.md` §7. Modeling a routine, expected risk denial as an exception would make
the normal "order didn't pass risk" case indistinguishable from a real programming error;
denial is a typed event/result instead. Reserve exceptions in this taxonomy for failures the
caller did not (and could not) already handle as a decision.
