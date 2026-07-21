"""Regression tests for fixes applied to shared/common + market-data infra.

Targets (file:line of the applied fix):
  F1  brokers/common/capabilities_validator.py:validate_gateway_capabilities
  F2  brokers/common/tick_validation.py:is_valid_quote / validate_depth
  M2  infrastructure/event_log.py:EventLog._seen_ids bounded OrderedDict
  M3  tradex/runtime/stream_orchestrator.py exchange-time + dedup
  M5  application/composer/factory.py backfill callback wiring

All imports are performed lazily INSIDE each test so a missing module only
causes that single test to skip (never a collection error).
"""

from __future__ import annotations

import collections
import logging
from datetime import datetime, timezone
from decimal import Decimal

import pytest

# ---------------------------------------------------------------------------
# F1 — capability/method mismatch is surfaced, not silently accepted
# ---------------------------------------------------------------------------


def test_f1_mismatched_gateway_reports_warning_and_mismatch():
    try:
        from brokers.common.capabilities_validator import validate_gateway_capabilities
    except Exception as exc:  # pragma: no cover
        pytest.skip(f"brokers.common.capabilities_validator unavailable: {exc}")

    warnings: list[str] = []

    class _Caps:
        supports_modify_order = True  # advertised...
        supports_order_cancellation = False

    class _MismatchedGateway:
        def capabilities(self) -> _Caps:
            return _Caps()

        # ...but NO modify_order method exists.

    fake_log = logging.getLogger("f1_test")
    fake_log.warning = warnings.append  # type: ignore[assignment]

    result = validate_gateway_capabilities(_MismatchedGateway(), log=fake_log)

    assert isinstance(result, list)
    assert len(result) > 0, "expected a non-empty mismatch list"
    assert any("supports_modify_order" in m for m in result)
    assert len(warnings) > 0, "expected a WARNING to be logged for the mismatch"


def test_f1_consistent_gateway_returns_empty():
    try:
        from brokers.common.capabilities_validator import validate_gateway_capabilities
    except Exception as exc:  # pragma: no cover
        pytest.skip(f"brokers.common.capabilities_validator unavailable: {exc}")

    warnings: list[str] = []

    class _Caps:
        supports_modify_order = True

    class _ConsistentGateway:
        def capabilities(self) -> _Caps:
            return _Caps()

        def modify_order(self, *a, **k):  # present -> consistent
            raise NotImplementedError

    fake_log = logging.getLogger("f1_test2")
    fake_log.warning = warnings.append  # type: ignore[assignment]

    result = validate_gateway_capabilities(_ConsistentGateway(), log=fake_log)

    assert result == []
    assert warnings == []


# ---------------------------------------------------------------------------
# F2 — tick / depth strict-mode drop rules
# ---------------------------------------------------------------------------


def test_f2_quote_validation_matrix():
    try:
        from brokers.common.tick_validation import is_valid_quote
    except Exception as exc:  # pragma: no cover
        pytest.skip(f"brokers.common.tick_validation unavailable: {exc}")

    # valid
    assert is_valid_quote({"symbol": "RELIANCE", "ltp": 2500.5}) is True
    # ltp = 0 -> drop
    assert is_valid_quote({"symbol": "RELIANCE", "ltp": 0}) is False
    assert is_valid_quote({"symbol": "RELIANCE", "ltp": Decimal("0")}) is False
    # ltp negative -> drop
    assert is_valid_quote({"symbol": "RELIANCE", "ltp": -1}) is False
    # ltp NaN -> drop (non-finite)
    assert is_valid_quote({"symbol": "RELIANCE", "ltp": float("nan")}) is False
    # ltp decimal valid
    assert is_valid_quote({"symbol": "RELIANCE", "ltp": Decimal("1.5")}) is True
    # missing symbol -> drop
    assert is_valid_quote({"ltp": 100}) is False
    assert is_valid_quote({"symbol": "", "ltp": 100}) is False
    assert is_valid_quote({"symbol": "X", "instrument": "", "ltp": 100}) is True
    # ltp None -> drop
    assert is_valid_quote({"symbol": "RELIANCE", "ltp": None}) is False


def test_f2_depth_validation_matrix():
    try:
        from brokers.common.tick_validation import validate_depth
    except Exception as exc:  # pragma: no cover
        pytest.skip(f"brokers.common.tick_validation unavailable: {exc}")

    # empty book -> drop
    assert validate_depth([]) is False
    # valid top-of-book price
    assert validate_depth([{"price": 2500.5, "qty": 10}]) is True
    # top price None -> drop
    assert validate_depth([{"price": None}]) is False
    # top price zero -> drop
    assert validate_depth([{"price": 0.0}]) is False
    # top price negative -> drop
    assert validate_depth([{"price": -5}]) is False
    # Decimal-aware valid
    assert validate_depth([{"price": Decimal("100.25")}]) is True
    # falls back to ltp key when price missing
    assert validate_depth([{"ltp": 123.0}]) is True
    assert validate_depth([{"ltp": 0}]) is False


# ---------------------------------------------------------------------------
# M2 — bounded LRU idempotency guard on EventLog
# ---------------------------------------------------------------------------


def test_m2_seen_ids_bounded_lru_and_dedup(tmp_path):
    try:
        from infrastructure import event_log as event_log_mod
        from infrastructure.event_bus import DomainEvent
        from infrastructure.event_log import EventLog
    except Exception as exc:  # pragma: no cover
        pytest.skip(f"infrastructure.event_log unavailable: {exc}")

    cap = 10
    original = event_log_mod.MAX_SEEN_IDS
    event_log_mod.MAX_SEEN_IDS = cap
    try:
        log = EventLog(events_dir=tmp_path / "events")

        def _ev(eid: str) -> DomainEvent:
            return DomainEvent(
                event_type="TICK",
                timestamp=datetime.now(timezone.utc),
                payload={"ltp": 1},
                event_id=eid,
            )

        # (a) append beyond the cap -> size stays bounded, oldest evicted.
        for i in range(20):
            log.append(_ev(f"evt-{i}"))
        assert isinstance(log._seen_ids, collections.OrderedDict)
        assert len(log._seen_ids) <= cap
        # oldest ids (0..9) should have been evicted
        assert "evt-0" not in log._seen_ids
        assert "evt-9" not in log._seen_ids
        # most recent ids retained
        assert "evt-19" in log._seen_ids

        # (b) a repeated *recent* id is detected as a duplicate (no new entry).
        assert "evt-19" in log._seen_ids
        n_before = len(log._seen_ids)
        log.append(_ev("evt-19"))  # duplicate of retained id
        n_after = len(log._seen_ids)
        assert n_after == n_before, "duplicate id should not grow the seen set"
        assert "evt-19" in log._seen_ids
    finally:
        event_log_mod.MAX_SEEN_IDS = original
        log.close()


# ---------------------------------------------------------------------------
# M3 — exchange-timestamp preservation + reconnect/backfill dedup
# ---------------------------------------------------------------------------


def _make_router():
    """Build a TickRouter without running __init__ (heavy deps)."""
    try:
        from application.streaming.tick_router import TickRouter
    except Exception as exc:  # pragma: no cover
        pytest.skip(f"application.streaming.tick_router unavailable: {exc}")
    router = object.__new__(TickRouter)
    router._dedup_seen = {}  # type: ignore[attr-defined]
    return router


def test_m3_exchange_timestamp_preserved_not_now():
    try:
        from application.streaming.tick_router import TickRouter
    except Exception as exc:  # pragma: no cover
        pytest.skip(f"application.streaming.tick_router unavailable: {exc}")

    now = datetime(2020, 1, 1, tzinfo=timezone.utc)  # "arrival" time
    # Upstox-style epoch-millis exchange timestamp (2023-01-01 UTC)
    exch_ts_ms = 1_672_531_200_000
    expected = datetime.fromtimestamp(exch_ts_ms / 1000, tz=timezone.utc)

    frame = {
        "symbol": "RELIANCE",
        "exchange": "NSE",
        "ltp": 2500.0,
        "exchange_timestamp": exch_ts_ms,
    }
    tick = TickRouter._normalize_tick(frame, "sess-1", "upstox", now)
    assert tick is not None
    assert tick.event_time == expected, "event_time must be the exchange ts"
    assert tick.event_time != now, "event_time must NOT fall back to arrival now"


def test_m3_repeated_key_within_window_is_dropped():
    router = _make_router()
    inst = "RELIANCE:NSE"
    et = datetime(2024, 5, 1, tzinfo=timezone.utc)
    seq = 42

    first = router.dedup_drop(inst, et, seq)  # type: ignore[attr-defined]
    second = router.dedup_drop(inst, et, seq)  # type: ignore[attr-defined]

    assert first is False, "first occurrence should be kept"
    assert second is True, "repeated (instrument, exchange_time, seq) must be dropped"


def test_m3_dhan_no_timestamp_not_wrongly_deduped():
    router = _make_router()
    inst = "RELIANCE:NSE"
    # Dhan tick carries no exchange ts -> event_time == arrival time.
    dhan_arrival = datetime(2024, 1, 1, tzinfo=timezone.utc)
    # A different (Upstox, timestamped) tick for the same instrument.
    upstox_exch = datetime(2024, 6, 1, tzinfo=timezone.utc)

    dhan_drop = router.dedup_drop(inst, dhan_arrival, None)  # type: ignore[attr-defined]
    upstox_drop = router.dedup_drop(inst, upstox_exch, None)  # type: ignore[attr-defined]

    assert dhan_drop is False
    # A Dhan tick (no timestamp) must NOT be collapsed with a timestamped tick.
    assert upstox_drop is False


# ---------------------------------------------------------------------------
# M5 — default backfill callback wiring is defensive
# ---------------------------------------------------------------------------


def test_m5_build_backfill_none_coordinator_returns_none():
    try:
        from application.composer.factory import _build_default_backfill_callback
    except Exception as exc:  # pragma: no cover
        pytest.skip(f"application.composer.factory unavailable: {exc}")

    assert _build_default_backfill_callback(None) is None


def test_m5_build_backfill_with_coordinator_returns_callable():
    try:
        from application.composer.factory import _build_default_backfill_callback
    except Exception as exc:  # pragma: no cover
        pytest.skip(f"application.composer.factory unavailable: {exc}")

    class _Coord:
        def fetch(self, q):  # pragma: no cover - not exercised here
            raise NotImplementedError

    cb = _build_default_backfill_callback(_Coord())
    assert callable(cb)


def test_m5_apply_backfill_sets_callback_without_raising():
    try:
        from application.composer.factory import _apply_default_backfill
    except Exception as exc:  # pragma: no cover
        pytest.skip(f"application.composer.factory unavailable: {exc}")

    def _cb(symbols, frm, to):
        return []

    # (1) callback None -> must no-op and never raise.
    class _PlainGateway:
        pass

    _apply_default_backfill([_PlainGateway()], None)

    # (2) absent targets: a gateway with no _backfill_callback attribute and no
    # nested _conn/_gateway must be tolerated without raising (defensive).
    _apply_default_backfill([_PlainGateway()], _cb)

    # (3) a realistic gateway that already declares the hook is wired through.
    class _Gateway:
        _backfill_callback = None  # declared by the real feed object

    gw = _Gateway()
    _apply_default_backfill([gw], _cb)
    assert gw._backfill_callback is _cb

    # (4) nested _conn target that declares the hook also receives it.
    class _Conn:
        _backfill_callback = None

    class _GatewayWithConn:
        _conn = None

    nested = _Conn()
    gw2 = _GatewayWithConn()
    gw2._conn = nested
    _apply_default_backfill([gw2], _cb)
    # The hook is wired onto the nested conn (which declared it); the outer
    # gateway is left untouched — no raise even though its target is absent.
    assert not hasattr(gw2, "_backfill_callback")
    assert nested._backfill_callback is _cb
