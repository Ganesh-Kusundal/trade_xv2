# Security Assessment

## Verdict

The platform has authentication, token lifecycle, secret-management, audit, API-key, and security-test infrastructure. It is not yet sufficient for a production money-moving control plane because authorization, secret handling, webhook authenticity, and audit durability are incomplete.

## Critical findings

### Unauthenticated token-ingestion webhook

The live webhook accepts an access token without signature verification or verified client/user/issued-at claims (`src/interface/api/routers/live/webhook.py:86-128`; mounted in `src/interface/api/routers/live/router.py:9-16`). Any reachable caller can submit token material. Require signed requests, replay protection, audience/issuer validation, and strict secret redaction.

### Plaintext tokens remain a supported default

Missing `SECRET_ENCRYPTION_KEY` enables unencrypted token files (`src/infrastructure/security/secret_manager.py:67-83,189-199,345-361`). Production readiness must fail closed when encryption/key management is absent. Use an external secret manager or OS/KMS-backed key, rotation, versioning, and revocation.

### Shared API key is not authorization

API auth has a shared key and a separate admin secret, but no user identity, roles, scopes, rotation, or per-action authorization (`src/interface/api/auth.py:131-175`). Feature-flag mutation claims admin-only but uses ordinary auth (`src/interface/api/routers/feature_flags.py:15,84-130`). Sensitive operations need explicit RBAC/ABAC and audit attribution.

### Audit is not authoritative

Audit emission is fire-and-forget; failures do not prevent state changes (`src/infrastructure/observability/audit.py:173-177`). Order intent, approval, submission outcome, and kill-switch events require durable append semantics and actor identity.

## Additional risks

- Missing API key generates an ephemeral key, causing restart invalidation and operator lockout (`src/interface/api/auth.py:57-76`).
- Observability HTTP server is unauthenticated by design (`src/infrastructure/observability/http_server.py:19-26`); deployment must guarantee private binding/network policy.
- Order validation is split between API schemas and broker validators (`src/interface/api/schemas.py:462-538`, `src/brokers/dhan/execution/order_validator.py:42-109`).
- Security tests can scan the wrong directory and pass without evaluating `src/` (`tests/unit/security/test_security_controls.py:18-24,62-68`).
- Secrets, tokens, broker responses, and error payloads need a repository-wide redaction contract, not scattered logging conventions.

## Required control-plane contract

Every sensitive operation must carry:

- authenticated principal and authorization decision;
- request ID and immutable idempotency key;
- validated instrument/order/risk intent;
- durable audit event before irreversible action;
- explicit response state: accepted, rejected, or unknown;
- revocation and recovery path.

The security bar for live trading is fail-closed: no encryption key, signature, authorization decision, or durable audit means no order mutation.
