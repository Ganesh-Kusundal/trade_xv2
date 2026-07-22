# TradeX V2

Event-driven trading kernel (paper / backtest / replay / live seam) under `v2/`.

## Install

```bash
cd v2
pip install -e ".[dev]"
# optional Upstox auto-login:
pip install -e ".[dev,upstox-totp]"
# or
make install
```

Requires Python ≥ 3.12. Core deps include `pyotp` for Dhan TOTP auto-token.

## Broker credentials (LIVE)

Dhan:

| Env | Purpose |
|-----|---------|
| `DHAN_CLIENT_ID` | Client id |
| `DHAN_ACCESS_TOKEN` | Static token (skip TOTP if set) |
| `DHAN_PIN` | PIN for TOTP generate |
| `DHAN_TOTP_SECRET` | TOTP secret |
| `DHAN_BASE_URL` | Default `https://api.dhan.co/v2` |
| `DHAN_TOKEN_PATH` | Persisted token JSON |

Upstox:

| Env | Purpose |
|-----|---------|
| `UPSTOX_CLIENT_ID` / `UPSTOX_CLIENT_SECRET` | OAuth app |
| `UPSTOX_ACCESS_TOKEN` | Static token |
| `UPSTOX_REFRESH_TOKEN` | Refresh grant |
| `UPSTOX_MOBILE` / `UPSTOX_PIN` / `UPSTOX_TOTP_SECRET` | Auto TOTP login (`upstox-totp`) |
| `UPSTOX_BASE_URL` | Default `https://api.upstox.com/v2` |
| `UPSTOX_TOKEN_PATH` | Persisted token JSON |

Rate limiting is multi-bucket (`orders` / `quotes` / `historical` / `admin`) at `HttpTransport`. TOTP generation is cooldown-guarded (Dhan 120s / Upstox 600s).

Live smoke (optional):

```bash
DHAN_ACCESS_TOKEN=... PYTHONPATH=src python -m pytest -m live -q
```

## Test

```bash
make test
# or
PYTHONPATH=src python -m pytest tests/ -q
```

Lint (ruff, if installed):

```bash
make lint
```

## Run CLI

Parent repo may also expose a `tradex` package — always prefer `PYTHONPATH=src` from this directory:

```bash
cd v2
PYTHONPATH=src python -m tradex.cli version
PYTHONPATH=src python -m tradex.cli config validate --config-dir config --profile paper
make cli
```
Paper session via TradingNode (see `tests/e2e/test_paper_session.py`):

```python
from tradex.node import TradingNode
node = TradingNode()
node.configure("config", profile="paper")
node.start()
node.stop()
```

## Docker

```bash
docker build -t tradex-v2 .
docker run --rm tradex-v2 version
```
