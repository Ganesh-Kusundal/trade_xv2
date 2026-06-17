# TradeXV2 Configuration

The `config/` directory holds broker credential templates and runtime
profile defaults. All `*.properties` files except `*.example` are
gitignored — copy the example template, fill in your credentials
locally, and never commit the result.

## Layout

```
config/
├── dhan-local.properties.example       Live Dhan (TOTP/JWT)
├── dhan-sandbox.properties.example     Sandbox Dhan
├── upstox-live.properties.example      Live Upstox (analytics + algo tokens)
├── upstox-sandbox.properties.example   Sandbox Upstox
├── icici-local.properties.example      ICICI Direct (Breeze, read-only)
├── scan-profiles.json                  Scan profile defaults (committed)
├── dhan-pin.txt                        (gitignored) TOTP PIN
└── dhan-totp-secret.txt                (gitignored) TOTP secret
```

## Profiles

| Profile | Credential files | Broker | Notes |
|---|---|---|---|
| `live-dhan` (default) | `config/dhan-local.properties` | Dhan LIVE | TOTP path; JWT bootstrap optional |
| `sandbox-dhan` | `config/dhan-sandbox.properties` | Dhan SANDBOX | `restBaseUrl=https://sandbox.dhan.co/v2` |
| `live-upstox` | `config/upstox-live.properties` | Upstox LIVE | Read-only routing preference in `IntelligentGateway`; **not** the live trading path |
| `sandbox-upstox` | `config/upstox-sandbox.properties` | Upstox SANDBOX | Read-only |
| `icici-prod` | `config/icici-local.properties` | ICICI Breeze LIVE | `ordersEnabled=false` by default |

## Loading

The Python-side `BrokerFactory.create(env_path=...)` reads
`dhan-local.properties` via the hand-rolled `_load_dotenv` parser in
`brokers/dhan/factory.py`. The CLI's `BrokerService._load_broker_env`
reads `.env.local` via `python-dotenv`. Both must agree on the
credential layout.

## Operational notes

* `dhan.pinFile` and `dhan.totpSecretFile` point at the gitignored
  text files in this directory. The factory uses `pyotp` with the
  shared `pyotp.TOTP(secret).now()` to generate the OTP.
* The token state JSON (`runtime-dev/dhan-token-state.json`) is
  auto-managed by `AuthManager`; the live JWT (`dhan.accessToken`)
  is rewritten atomically via `fcntl.flock` + temp+rename.
* The Upstox analytics token is a 1-year read-only credential and is
  used by `IntelligentGateway` for LTP/Quote preference; falls back
  to Dhan on failure.
* `scan-profiles.json` is committed (no secrets) and is the canonical
  scan-profile source for the analytics engine.
