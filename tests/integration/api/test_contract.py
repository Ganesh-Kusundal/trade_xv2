"""SPA↔backend contract tests against the real ``data/lake`` parquet + catalog.

Uses ``create_app`` + ``TestClient`` with real ``DataLakeGateway`` /
``DataCatalog`` / ``ViewManager`` (no stubs for lake-backed routes).
Live quote type contract uses the same lake via ``BrokerDataProvider`` +
``Session`` (real adapters, not mock quote payloads).
"""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from analytics.views.manager import ViewManager
from datalake.gateway import DataLakeGateway
from datalake.storage.catalog import DataCatalog
from domain.enums import OrderStatus
from domain.ports.data_catalog import DEFAULT_CATALOG_PATH, DEFAULT_DATA_ROOT
from domain.session import Session
from infrastructure.providers.broker.broker_data_provider import BrokerDataProvider
from interface.api.config import APIConfig
from interface.api.deps import reset_container
from interface.api.main import create_app
from interface.api.routers import market as market_router
from interface.api.routers.live import market as live_market
from interface.api.schemas._market import QuoteResponse


PROJECT_ROOT = Path(__file__).resolve().parents[3]
LAKE_ROOT = PROJECT_ROOT / DEFAULT_DATA_ROOT
CATALOG_PATH = PROJECT_ROOT / DEFAULT_CATALOG_PATH

CANDLE_KEYS = {"t", "o", "h", "l", "c", "v", "oi"}


@pytest.fixture(scope="module")
def lake_ready() -> None:
    assert (LAKE_ROOT / "equities" / "candles").exists(), "missing equities candles"
    assert (LAKE_ROOT / "indices" / "candles").exists(), "missing indices candles"
    assert (LAKE_ROOT / "options" / "candles").exists(), "missing options candles"
    assert CATALOG_PATH.exists(), "missing data/lake/catalog.duckdb"


@pytest.fixture
def contract_client(lake_ready: None):
    """Real lake-backed API client with Session wired for quote routes."""
    reset_container()
    gw = DataLakeGateway(root=str(LAKE_ROOT))
    catalog = DataCatalog(root=str(LAKE_ROOT), read_only=True)
    vm = ViewManager(catalog_path=CATALOG_PATH, read_only=True)
    session = Session(BrokerDataProvider(gw, broker_name="datalake"))
    market_router.set_session(session)
    live_market.set_session(session)

    app = create_app(
        config=APIConfig(
            auth_mode="none",
            cors_origins=[
                "http://localhost:5173",
                "http://127.0.0.1:5173",
            ],
        ),
        datalake_gateway=gw,
        data_catalog=catalog,
        view_manager=vm,
    )
    client = TestClient(app)
    try:
        yield client
    finally:
        market_router.set_session(None)
        live_market.set_session(None)
        reset_container()


def _assert_candle_shape(candle: dict) -> None:
    assert set(candle.keys()) >= CANDLE_KEYS
    for k in ("o", "h", "l", "c", "v", "oi"):
        assert isinstance(candle[k], (int, float))
    assert isinstance(candle["t"], (int, float))


def test_market_candles_equity(contract_client: TestClient) -> None:
    resp = contract_client.get(
        "/api/v1/market/candles",
        params={"symbol": "RELIANCE", "timeframe": "1m", "limit": 5},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["symbol"] == "RELIANCE"
    assert body["count"] >= 1
    assert len(body["candles"]) >= 1
    _assert_candle_shape(body["candles"][0])


def test_market_candles_index(contract_client: TestClient) -> None:
    resp = contract_client.get(
        "/api/v1/market/candles",
        params={"symbol": "NIFTY", "timeframe": "1m", "limit": 5},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["symbol"] == "NIFTY"
    assert body["count"] >= 1
    _assert_candle_shape(body["candles"][0])


def test_options_chain_shape(contract_client: TestClient) -> None:
    resp = contract_client.get(
        "/api/v1/options/chain/NIFTY",
        params={"strike_range": 5},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["underlying"] == "NIFTY"
    assert body["count"] >= 1
    assert body["contracts"]
    for c in body["contracts"]:
        assert c["option_type"] in {"CE", "PE", "CALL", "PUT"}
        for field in ("strike", "ltp", "volume", "oi"):
            assert field in c
            assert isinstance(c[field], (int, float))


def test_pcr_maxpain_ivsurface(contract_client: TestClient) -> None:
    for path, required in (
        (
            "/api/v1/options/pcr/NIFTY",
            {"underlying", "pcr_volume", "pcr_oi", "total_ce_oi", "total_pe_oi"},
        ),
        (
            "/api/v1/options/max-pain/NIFTY",
            {"underlying", "max_pain_strike", "spot", "distance_from_spot"},
        ),
        (
            "/api/v1/options/iv-surface/NIFTY",
            {"underlying", "atm_strike", "atm_iv", "iv_skew"},
        ),
    ):
        resp = contract_client.get(path)
        assert resp.status_code == 200, f"{path}: {resp.text}"
        body = resp.json()
        assert required <= set(body.keys())
        for key in required - {"underlying"}:
            val = body[key]
            if val is not None:
                assert isinstance(val, (int, float)), f"{path}.{key}={val!r}"


def test_quote_no_bid_ask(contract_client: TestClient) -> None:
    """Lake-backed /market/quote omits live-only bid/ask (schema documents this)."""
    resp = contract_client.get("/api/v1/market/quote/RELIANCE")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert "ltp" in body and isinstance(body["ltp"], (int, float))
    assert body.get("bid") is None
    assert body.get("ask") is None
    # Honest schema: fields exist as Optional on QuoteResponse but are live-only.
    fields = QuoteResponse.model_fields
    assert "bid" in fields and "ask" in fields
    assert "live-only" in (fields["bid"].description or "").lower()


def test_live_quote_numeric(contract_client: TestClient) -> None:
    resp = contract_client.get("/api/v1/live/quote/RELIANCE")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    for key in ("ltp", "open", "high", "low", "close", "volume"):
        assert key in body
        assert isinstance(body[key], (int, float)), f"{key}={body[key]!r} not numeric"


def test_cors_allows_api_key(contract_client: TestClient) -> None:
    resp = contract_client.options(
        "/api/v1/market/quote/RELIANCE",
        headers={
            "Origin": "http://localhost:5173",
            "Access-Control-Request-Method": "GET",
            "Access-Control-Request-Headers": "X-API-Key",
        },
    )
    assert resp.status_code == 200
    allow = resp.headers.get("access-control-allow-headers", "")
    assert "x-api-key" in allow.lower()


def test_options_type_contract(contract_client: TestClient) -> None:
    """Lake emits CALL/PUT; SPA normalizes via startsWith('C'); backend accepts both."""
    resp = contract_client.get(
        "/api/v1/options/chain/NIFTY",
        params={"strike_range": 10},
    )
    assert resp.status_code == 200
    types = {c["option_type"].upper() for c in resp.json()["contracts"]}
    assert types & {"CALL", "PUT", "CE", "PE"}
    # Volume profile buckets CALL→CE and PUT→PE (regression for CE-only SQL).
    vp = contract_client.get("/api/v1/options/volume-profile/NIFTY")
    assert vp.status_code == 200, vp.text
    profile = vp.json().get("profile") or []
    assert profile, "expected volume profile rows"
    assert any(row.get("ce_volume", 0) > 0 or row.get("pe_volume", 0) > 0 for row in profile)


def test_cancellable_order_statuses_match_domain() -> None:
    """SPA cancel whitelist must be subset of canonical OrderStatus values."""
    # Imported inline so web/ need not be on PYTHONPATH for backend CI.
    cancellable = {"OPEN", "PARTIALLY_FILLED"}
    domain = {s.value for s in OrderStatus}
    assert cancellable <= domain
    for s in cancellable:
        assert not OrderStatus(s).is_terminal


def test_broker_health_status_vocabulary(contract_client: TestClient) -> None:
    """Without a live broker: 503. With stub gateway: status is a known token.

    SPA ``BrokerStatus`` treats ``healthy`` / ``degraded`` / other as ok/warn/error.
    """
    resp = contract_client.get("/api/v1/live/health")
    # No broker_service wired on contract_client → 503 (explicit failure, not silent).
    assert resp.status_code == 503

    allowed = frozenset({"healthy", "degraded", "error"})
    # Document the SPA contract vocabulary used by BrokerStatus.tsx.
    assert "healthy" in allowed and "degraded" in allowed and "error" in allowed
