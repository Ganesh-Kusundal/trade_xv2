# TradeXV2 Configuration

Runtime credentials live in **env files at the project root**, not in
`config/*.properties`.  The `config/` directory holds TOTP secret files
and example templates only.

## Canonical credential layout

| Broker | Env file | TOTP / secret files |
|--------|----------|---------------------|
| Dhan (live) | `.env.local` | `config/dhan-pin.txt`, `config/dhan-totp-secret.txt` |
| Upstox (live) | `.env.upstox` | `UPSTOX_PIN` / `UPSTOX_TOTP_SECRET` in env or SecretsManager |
| Paper | *(none)* | N/A |

Copy `.env.example` to `.env.local` and fill in Dhan values.  For Upstox,
copy the Upstox section to `.env.upstox` (or maintain a separate file).

```
project-root/
├── .env.local              # Dhan: DHAN_CLIENT_ID, DHAN_ACCESS_TOKEN, TOTP paths
├── .env.upstox             # Upstox: UPSTOX_CLIENT_ID, UPSTOX_ACCESS_TOKEN, etc.
├── config/
│   ├── dhan-pin.txt        # (gitignored) TOTP PIN
│   ├── dhan-totp-secret.txt
│   └── *.properties.example  # Reference templates only — not loaded at runtime
└── runtime/
    └── dhan-token-state.json   # AuthManager persistence (auto-managed)
```

## Loading

1. **CLI** (`cli/main.py`) loads both `.env.local` and `.env.upstox` at startup via `bootstrap_environment()`.
2. **API** (`api_server.py`) calls the same helper before service init.
2. **Broker registry** (`cli/services/broker_registry.py`) resolves paths via
   :class:`brokers.common.auth.credential_resolver.CredentialResolver`.
3. **Dhan factory** (`brokers/dhan/factory.py`) uses
   :class:`DhanSettingsLoader` + :class:`AuthManager` with
   `runtime/dhan-token-state.json`.
4. **Upstox factory** loads **only** `.env.upstox` when called through the
   registry (not `.env.local`).

`list_available_brokers()` checks credential **content**, not just file
existence, via :class:`brokers.common.auth.credential_validator.CredentialValidator`.

## Operational notes

* `DHAN_PIN_FILE` / `DHAN_TOTP_SECRET_FILE` may point at gitignored files
  under `config/`.
* Dhan tokens are refreshed via TOTP POST (body, not URL query) only when
  missing, expired, or broker-rejected. Valid tokens in
  `runtime/dhan-token-state.json` are reused without calling TOTP.
* `.env.local` `DHAN_ACCESS_TOKEN` is a write-through mirror; canonical
  store is `runtime/dhan-token-state.json` (JWT `exp` drives expiry).
* Background :class:`TokenRefreshScheduler` refreshes only expired tokens,
  not on proximity buffer alone.
* Upstox analytics tokens are read-only; set `UPSTOX_ANALYTICS_ONLY=1` for
  market-data-only routing.  Live orders require `UPSTOX_ALLOW_LIVE_ORDERS=1`.
* `scan-profiles.json` is committed (no secrets) and is the canonical
  scan-profile source for the analytics engine.

## Legacy `*.properties` templates

Files such as `config/dhan-local.properties.example` document field names
for migration from Trade_J.  They are **not** read by the Python runtime.
Use `.env.local` / `.env.upstox` instead.
