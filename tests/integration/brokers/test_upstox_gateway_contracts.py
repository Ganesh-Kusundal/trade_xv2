"""Regression tests pinning the applied Upstox remediation fixes.

All product-module imports are performed lazily INSIDE each test so that a
missing/optional dependency causes a clean ``pytest.skip`` at collection or
runtime rather than a hard import error.  Network/token boundaries are faked;
no live Upstox calls are made.

Fixes pinned:
  * G2  brokers/providers/upstox/broker.py  `_build_order_path` wires ``portfolio_stream``
       and defines ``_ensure_extended`` / ``_extended_ready``; gateway
       ``stream_order`` and ``extended`` no longer raise ``AttributeError``.
  * R4  brokers/providers/upstox/auth/http.py  finite rate-limiter timeout + 429/5xx/
       network retry with backoff (honours ``Retry-After``).
  * R5  brokers/providers/upstox/orders/order_command_adapter.py  ``modify_order`` raises
       ``ValueError`` (clear message) when instrument_key cannot be resolved
       instead of sending a bad request.
  * R6  brokers/providers/upstox/websocket/market_data_v3.py  ``_tick_quote_is_valid``
       drops invalid quotes via ``is_valid_quote``; translator in
       brokers/providers/upstox/adapters/tick_translator.py.
"""

from __future__ import annotations

import time

import pytest


def _needs_module(module: str) -> None:
    """Skip the calling test if *module* cannot be imported."""
    try:
        __import__(module)
    except Exception as exc:
        pytest.skip(f"optional module {module!r} unavailable: {exc}")


# ── G2 ─────────────────────────────────────────────────────────────────────


def _make_broker_and_gateway():
    """Construct a real (offline) UpstoxBroker + gateway, or skip."""
    from brokers.providers.upstox.auth.config import UpstoxConnectionSettings
    from brokers.providers.upstox.broker import UpstoxBroker
    from brokers.providers.upstox.wire import UpstoxWireAdapter

    settings = UpstoxConnectionSettings(client_id="regression-test", access_token="dummy-token")
    broker = UpstoxBroker(settings)
    gateway = UpstoxWireAdapter(broker)
    return broker, gateway


def test_g2_portfolio_stream_and_stream_order() -> None:
    """portfolio_stream is wired and gateway.stream_order does not raise."""
    _needs_module("brokers.providers.upstox.broker")

    broker, gateway = _make_broker_and_gateway()

    # (a) portfolio_stream attribute exists (was AttributeError before the fix).
    assert hasattr(broker, "portfolio_stream"), "broker.portfolio_stream missing"

    # gateway.stream_order must be reachable and callable without AttributeError.
    assert callable(gateway.stream_order)

    # Avoid a real network connect: force the portfolio stream to report
    # "already connected" so stream_order merely registers a listener.
    stream = broker.portfolio_stream
    type(stream).is_connected = property(lambda self: True)  # type: ignore[assignment]
    handle = gateway.stream_order()
    assert handle is not None


def test_g2_extended_capabilities() -> None:
    """gateway.extended returns a working UpstoxExtendedCapabilities (G2b)."""
    _needs_module("brokers.providers.upstox.extended")

    from brokers.providers.upstox.extended import UpstoxExtendedCapabilities

    broker, gateway = _make_broker_and_gateway()

    # Accessing the property must not raise AttributeError and must yield a
    # usable capabilities object; constructing it triggers _ensure_extended.
    ext = gateway.extended
    assert isinstance(ext, UpstoxExtendedCapabilities)

    # _ensure_extended must complete without error and flip the ready flag.
    broker._ensure_extended()
    assert broker._extended_ready is True


# ── R4 ─────────────────────────────────────────────────────────────────────


def _make_http_client(rate_limiter):
    """Build a UpstoxHttpClient with a controllable rate limiter (no network)."""
    from brokers.providers.upstox.auth.http import UpstoxHttpClient

    return UpstoxHttpClient(
        lambda: "dummy-bearer-token",
        object(),  # settings: only read via getattr with defaults
        rate_limiter=rate_limiter,
        rate_limit_timeout_seconds=0.01,
    )


class _FakeResponse:
    def __init__(self, status_code: int, text: str = "{}", retry_after: float | None = None):
        self.status_code = status_code
        self.text = text
        self.headers: dict[str, str] = {}
        if retry_after is not None:
            self.headers["Retry-After"] = str(retry_after)

    def json(self):
        return {"status": "success", "data": {"ok": True}}


class _FakeSession:
    """Returns queued responses in order, then 200 forever."""

    def __init__(self, responses):
        self._responses = list(responses)
        self.calls = 0

    def request(self, **kwargs):
        self.calls += 1
        if self._responses:
            return self._responses.pop(0)
        return _FakeResponse(200)


def test_r4_retries_429_then_succeeds() -> None:
    """429 then 200 must eventually succeed after backoff (R4)."""
    _needs_module("brokers.providers.upstox.auth.http")

    class _AcquireTrue:
        def acquire(self, bucket, tokens=1, timeout=None):
            return True

    client = _make_http_client(_AcquireTrue())
    # Neutralise backoff so the test is fast and deterministic.
    client._backoff = lambda *a, **k: None  # type: ignore[assignment]
    client._session = _FakeSession([_FakeResponse(429), _FakeResponse(200)])

    result = client.get_json("https://api.upstox.com/market-quote")
    assert result.get("status") == "success"
    assert client._session.calls == 2


def test_r4_finite_rate_limit_timeout_raises_not_hangs() -> None:
    """A finite acquire timeout must raise (not block forever) (R4)."""
    _needs_module("brokers.providers.upstox.auth.http")
    from brokers.providers.upstox.auth.exceptions import UpstoxApiError

    class _AcquireFalse:
        def acquire(self, bucket, tokens=1, timeout=None):
            # Simulate the limiter timing out (would block forever if None).
            return False

    client = _make_http_client(_AcquireFalse())
    client._rate_limit_timeout = 0.01

    start = time.monotonic()
    with pytest.raises(UpstoxApiError):
        client.get_json("https://api.upstox.com/market-quote")
    elapsed = time.monotonic() - start
    # Must fail fast (finite timeout) rather than hang.
    assert elapsed < 5.0


# ── R5 ─────────────────────────────────────────────────────────────────────


def test_r5_modify_order_raises_value_error_when_key_unresolved() -> None:
    """modify_order raises ValueError (no bad request) when key can't resolve."""
    _needs_module("brokers.providers.upstox.orders.order_command_adapter")
    from brokers.providers.upstox.instruments.resolver import UpstoxInstrumentResolver
    from brokers.providers.upstox.orders.order_command_adapter import UpstoxOrderCommandAdapter

    class _FailingOrderClient:
        def get_order(self, order_id):
            # Lookup fails -> instrument_key cannot be resolved.
            raise ValueError("order lookup failed")

        def modify_order_v3(self, payload):
            # Must NOT be reached: sending order_id without instrument_key.
            raise AssertionError("bad modify request was sent to the broker")

    adapter = UpstoxOrderCommandAdapter(
        _FailingOrderClient(),
        UpstoxInstrumentResolver(),
    )

    with pytest.raises(ValueError) as excinfo:
        adapter.modify_order("ORD123")

    assert "instrument_key" in str(excinfo.value).lower()


# ── R6 ─────────────────────────────────────────────────────────────────────


def test_r6_is_valid_quote_drop_rules() -> None:
    """Shared drop rule backs the fix: zero/negative/missing-symbol dropped."""
    _needs_module("brokers.common.tick_validation")
    from brokers.common.tick_validation import is_valid_quote

    assert is_valid_quote({"ltp": 0, "symbol": "X"}) is False
    assert is_valid_quote({"ltp": -1, "symbol": "X"}) is False
    assert is_valid_quote({"ltp": 10, "symbol": ""}) is False
    assert is_valid_quote({"ltp": 10, "symbol": "RELIANCE"}) is True


def test_r6_tick_quote_is_valid_drops_invalid_forwards_valid() -> None:
    """Multiplexer drops invalid quotes, forwards valid ones (R6)."""
    _needs_module("brokers.providers.upstox.websocket.market_data_v3")
    from brokers.providers.upstox.websocket.market_data_v3 import UpstoxMarketDataV3Multiplexer

    # The translator layer receives the {payload: ...} wrapper (same shape the
    # downstream tick listener gets); this exercises the is_valid_quote drop
    # delegation inside _tick_quote_is_valid.
    class _Frame:
        def __init__(self, payload):
            self.payload = payload

    mux = UpstoxMarketDataV3Multiplexer(authorizer=object())

    valid = _Frame({"payload": {"instrument_key": "NSE_EQ|INE002A01018", "ltp": 100}})
    zero = _Frame({"payload": {"instrument_key": "NSE_EQ|INE002A01018", "ltp": 0}})
    neg = _Frame({"payload": {"instrument_key": "NSE_EQ|INE002A01018", "ltp": -5}})

    assert mux._tick_quote_is_valid(valid) is True
    assert mux._tick_quote_is_valid(zero) is False
    assert mux._tick_quote_is_valid(neg) is False


def test_r6_raw_dict_tick_dropped_when_invalid() -> None:
    """Raw (untranslated) ticks with an extractable invalid LTP are dropped (R6 gap fix).

    Previously frames the translator could not parse were forwarded as-is,
    letting a zero/negative LTP raw dict slip through validation.
    """
    _needs_module("brokers.providers.upstox.websocket.market_data_v3")
    from brokers.providers.upstox.websocket.market_data_v3 import UpstoxMarketDataV3Multiplexer

    class _Frame:
        def __init__(self, payload):
            self.payload = payload

    mux = UpstoxMarketDataV3Multiplexer(authorizer=object())

    # Raw dict ticks (payload is the tick dict directly, not wrapped).
    raw_zero = _Frame({"ltp": 0, "symbol": "RELIANCE"})
    raw_valid = _Frame({"ltp": 2500, "symbol": "RELIANCE"})
    raw_opaque = _Frame({"foo": "bar"})  # no extractable LTP -> forward as-is

    assert mux._tick_quote_is_valid(raw_zero) is False
    assert mux._tick_quote_is_valid(raw_valid) is True
    assert mux._tick_quote_is_valid(raw_opaque) is True
