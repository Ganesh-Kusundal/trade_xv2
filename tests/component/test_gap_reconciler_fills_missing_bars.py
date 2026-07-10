"""Regression test for the SESSION-GAP reconciler (beyond M5 reconnect backfill).

Targets:
  - application/composer/gap_reconciler.py  GapReconciler
  - application/composer/factory.py        _build_default_backfill_callback
                                           (now triggers a reconcile after backfill)

The reconciler must:
  1. Detect the missing time range for a subscribed instrument (between the
     last locally-known sample and now, minus what a reconnect backfill already
     covered) and request it from the HistoricalDataCoordinator.
  2. "Fill" it by invoking the fill callback with the gap bars.
  3. Be a no-op when no coordinator is configured.

All imports are lazy inside each test so a missing module only skips that test
(never a collection error).
"""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone


def _make_bar(ts: datetime, close: float = 100.0):
    """Build a minimal fake HistoricalBar understood by factory._bar_to_dict."""
    from types import SimpleNamespace

    instrument = SimpleNamespace(symbol="RELIANCE", exchange="NSE")
    return SimpleNamespace(
        event_time=ts,
        open=close,
        high=close,
        low=close,
        close=close,
        volume=10,
        instrument=instrument,
    )


def _make_fake_coordinator(captured: dict, bars: list):
    """Return a fake HistoricalDataCoordinator whose fetch records the query."""

    class _Ledger:  # noqa: D401 - tiny stub
        degraded = False

    class _Coord:  # noqa: D401 - tiny stub
        async def fetch(self, query):
            captured["query"] = query
            captured["instrument"] = query.instrument
            captured["timeframe"] = query.timeframe
            captured["from_date"] = query.from_date
            captured["to_date"] = query.to_date
            series = type("_Series", (), {"bars": bars})()
            return series, _Ledger()

    return _Coord()


# ---------------------------------------------------------------------------
# Core: detect + fill
# ---------------------------------------------------------------------------


def test_gap_reconciler_detects_and_fills_gap():
    try:
        from application.composer.gap_reconciler import GapReconciler
    except Exception as exc:  # pragma: no cover
        __import__("pytest").skip(f"gap_reconciler unavailable: {exc}")

    captured: dict = {}
    now = datetime(2024, 1, 5, 12, 0, tzinfo=timezone.utc)
    last_known = datetime(2024, 1, 1, 10, 0, tzinfo=timezone.utc)

    filled: dict[str, list] = {}

    def _last_known(key):
        return last_known

    def _fill(key, bars):
        filled[key] = bars

    bars = [_make_bar(datetime(2024, 1, 2, tzinfo=timezone.utc))]
    coord = _make_fake_coordinator(captured, bars)
    reconciler = GapReconciler(coord, last_known_fn=_last_known, fill_callback=_fill)

    results = reconciler.reconcile(["RELIANCE:NSE"], now=now)

    # (1) Detected the right range: from last-known date to "now" date.
    assert captured["from_date"] == date(2024, 1, 1)
    assert captured["to_date"] == date(2024, 1, 5)
    assert captured["instrument"].symbol == "RELIANCE"
    assert captured["instrument"].exchange == "NSE"

    # (2) "Filled" it: the fill callback was invoked with the gap bars
    # (normalized to tick dicts by factory._bar_to_dict).
    assert "RELIANCE:NSE" in filled
    assert len(filled["RELIANCE:NSE"]) == 1
    assert filled["RELIANCE:NSE"][0]["symbol"] == "RELIANCE"
    assert filled["RELIANCE:NSE"][0]["close"] == 100.0
    assert len(results) == 1
    assert results[0]["bar_count"] == 1


# ---------------------------------------------------------------------------
# already_covered_to subtracts the reconnect backfill range
# ---------------------------------------------------------------------------


def test_gap_reconciler_subtracts_already_covered():
    try:
        from application.composer.gap_reconciler import GapReconciler
    except Exception as exc:  # pragma: no cover
        __import__("pytest").skip(f"gap_reconciler unavailable: {exc}")

    captured: dict = {}
    now = datetime(2024, 1, 5, 12, 0, tzinfo=timezone.utc)
    last_known = datetime(2024, 1, 1, 10, 0, tzinfo=timezone.utc)
    already_covered = datetime(2024, 1, 4, 0, 0, tzinfo=timezone.utc)

    def _last_known(key):
        return last_known

    bars = [_make_bar(datetime(2024, 1, 4, tzinfo=timezone.utc))]
    coord = _make_fake_coordinator(captured, bars)
    reconciler = GapReconciler(coord, last_known_fn=_last_known, fill_callback=lambda k, b: None)

    reconciler.reconcile(
        ["RELIANCE:NSE"], now=now, already_covered_to={"RELIANCE:NSE": already_covered}
    )

    # Gap start should have been advanced to the already-covered time.
    assert captured["from_date"] == date(2024, 1, 4)
    assert captured["to_date"] == date(2024, 1, 5)


# ---------------------------------------------------------------------------
# No coordinator -> no-op
# ---------------------------------------------------------------------------


def test_gap_reconciler_no_coordinator_is_noop():
    try:
        from application.composer.gap_reconciler import GapReconciler
    except Exception as exc:  # pragma: no cover
        __import__("pytest").skip(f"gap_reconciler unavailable: {exc}")

    filled: dict = {}

    def _fill(key, bars):
        filled[key] = bars

    reconciler = GapReconciler(None, fill_callback=_fill)
    results = reconciler.reconcile(["RELIANCE:NSE"], now=datetime(2024, 1, 5, tzinfo=timezone.utc))

    assert results == []
    assert filled == {}


# ---------------------------------------------------------------------------
# Bounds: max_instruments is respected
# ---------------------------------------------------------------------------


def test_gap_reconciler_respects_max_instruments():
    try:
        from application.composer.gap_reconciler import GapReconciler
    except Exception as exc:  # pragma: no cover
        __import__("pytest").skip(f"gap_reconciler unavailable: {exc}")

    captured: list = []
    now = datetime(2024, 1, 5, tzinfo=timezone.utc)
    bars = [_make_bar(datetime(2024, 1, 2, tzinfo=timezone.utc))]

    def _coord_factory():
        c: dict = {}
        return _make_fake_coordinator(c, bars), c

    coord, _ = _coord_factory()
    reconciler = GapReconciler(
        coord, max_instruments=3, fill_callback=lambda k, b: captured.append(k)
    )
    many = [f"SYM{i}:NSE" for i in range(10)]
    reconciler.reconcile(many, now=now)

    assert len(captured) == 3


# ---------------------------------------------------------------------------
# Factory wiring: backfill callback triggers reconcile (requirement b)
# ---------------------------------------------------------------------------


def test_m5_backfill_with_reconciler_triggers_reconcile():
    try:
        from application.composer.factory import _build_default_backfill_callback
    except Exception as exc:  # pragma: no cover
        __import__("pytest").skip(f"application.composer.factory unavailable: {exc}")

    class _Coord:
        async def fetch(self, q):
            class _S:  # noqa: D401
                bars = []

            class _L:  # noqa: D401
                degraded = False

            return _S(), _L()

    calls: list = []

    class _FakeReconciler:
        def reconcile(self, subscribed, *, now=None, already_covered_to=None):
            calls.append((list(subscribed), already_covered_to))
            return []

    from_dt = datetime(2024, 1, 1, tzinfo=timezone.utc)
    to_dt = datetime(2024, 1, 5, tzinfo=timezone.utc)

    cb = _build_default_backfill_callback(_Coord(), gap_reconciler=_FakeReconciler())
    out = cb("RELIANCE:NSE", from_dt, to_dt)

    # Backfill still returns its own (empty) result...
    assert out == []
    # ...and the session reconciler was triggered once, with the backfill
    # range passed as already_covered_to.
    assert len(calls) == 1
    assert calls[0][0] == ["RELIANCE:NSE"]
    assert calls[0][1] == {"RELIANCE:NSE": to_dt}


def test_m5_backfill_no_coordinator_still_noop_with_reconciler():
    try:
        from application.composer.factory import _build_default_backfill_callback
    except Exception as exc:  # pragma: no cover
        __import__("pytest").skip(f"application.composer.factory unavailable: {exc}")

    class _FakeReconciler:
        def reconcile(self, *a, **k):  # pragma: no cover
            raise AssertionError("reconcile must not run without a coordinator")

    # Coordinator is None -> callback must be None regardless of reconciler arg.
    assert _build_default_backfill_callback(None, gap_reconciler=_FakeReconciler()) is None
