# Security Policy

## Supported versions

| Version | Supported |
|---|---|
| 0.2.x (Phase 9+ release) | ✅ |
| 0.1.x (current) | ⚠️ Best-effort |

## Reporting a vulnerability

**Please do NOT open a public GitHub issue for security vulnerabilities.**

Instead, please email **security@tradexv2.example.com** with:
- Description of the vulnerability
- Steps to reproduce
- Potential impact
- Suggested fix (if any)

We will:
- Acknowledge within 48 hours
- Provide an initial assessment within 5 business days
- Coordinate disclosure timing with you

## Secrets management

**Never commit**:
- API keys, secrets, or tokens
- `.env.local` files
- `*_token.json` files
- `config/*.secret` files

The `.gitignore` should catch most of these. If you accidentally commit
a secret, **rotate it immediately** and email the security contact.

## Trading-specific concerns

- **Never disable** pre-trade risk checks in production.
- **Never bypass** the kill switch.
- **Always use** the live trading gate (no direct broker calls from CLI in LIVE mode).
- **Always log** order placements, modifications, and cancellations to the audit log.

## Dependencies

We use Dependabot to monitor dependencies. To audit locally:
```bash
pip install pip-audit
pip-audit
```
