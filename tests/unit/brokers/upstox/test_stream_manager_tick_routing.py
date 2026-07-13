"""StreamManagerAdapter tick routing — regression guard.

``ws.add_listener()`` registers a connection-wide listener (not one scoped
to a single instrument), so every subscriber's ``wrapped_listener`` used to
fire for every tick on the shared WebSocket regardless of which instrument
it was about. Subscribing to two symbols meant every callback received
every other symbol's ticks too. Fixed by filtering the raw tick's
instrument_key against the subscription's own key before invoking the
caller's callback.
"""

from __future__ import annotations

from brokers.upstox.adapters.stream_manager import StreamManagerAdapter


class FakeWebSocket:
    def __init__(self):
        self.listeners = []
        self.is_connected = True
        self.subscribed_keys = []

    def add_listener(self, listener):
        self.listeners.append(listener)

    def subscribe(self, keys, mode):
        self.subscribed_keys.extend(keys)

    def remove_listener(self, listener):
        self.listeners.remove(listener)

    def unsubscribe(self, keys):
        pass

    def emit(self, instrument_key: str, **fields):
        """Simulate the shared WS delivering a tick to every listener."""
        payload = {"instrument_key": instrument_key, **fields}
        for listener in list(self.listeners):
            listener("feed", payload)


class FakeInstruments:
    def __init__(self, keys: dict[tuple[str, str], str]):
        self._keys = keys

    def resolve_instrument_key(self, symbol: str, exchange: str) -> str:
        return self._keys[(symbol, exchange)]


class FakeBroker:
    def __init__(self, ws: FakeWebSocket, keys: dict[tuple[str, str], str]):
        self.market_data_websocket = ws
        self.instruments = FakeInstruments(keys)


class FakeResolver:
    def resolve(self, instrument_key: str):
        return None


def _make_manager():
    ws = FakeWebSocket()
    keys = {
        ("RELIANCE", "NSE"): "NSE_EQ|INE002A01018",
        ("CRUDEOIL", "MCX"): "MCX_FO|520702",
    }
    broker = FakeBroker(ws, keys)
    manager = StreamManagerAdapter(broker, instrument_resolver=FakeResolver())
    return manager, ws


def test_tick_only_delivered_to_matching_subscriber():
    manager, ws = _make_manager()
    reliance_ticks = []
    crude_ticks = []

    manager.subscribe("RELIANCE", "NSE", "LTP", on_tick=reliance_ticks.append)
    manager.subscribe("CRUDEOIL", "MCX", "LTP", on_tick=crude_ticks.append)

    ws.emit("NSE_EQ|INE002A01018", last_price=1296.9)

    assert len(reliance_ticks) == 1
    assert len(crude_ticks) == 0, "CRUDEOIL callback must not receive RELIANCE's tick"


def test_each_symbol_only_sees_its_own_ticks():
    manager, ws = _make_manager()
    reliance_ticks = []
    crude_ticks = []

    manager.subscribe("RELIANCE", "NSE", "LTP", on_tick=reliance_ticks.append)
    manager.subscribe("CRUDEOIL", "MCX", "LTP", on_tick=crude_ticks.append)

    ws.emit("NSE_EQ|INE002A01018", last_price=1296.9)
    ws.emit("MCX_FO|520702", last_price=7090.0)
    ws.emit("NSE_EQ|INE002A01018", last_price=1297.0)

    assert len(reliance_ticks) == 2
    assert len(crude_ticks) == 1


def test_unsubscribe_uses_same_key_as_subscribe():
    """unsubscribe() must resolve the identical instrument_key subscribe()
    used, or it looks up the wrong registry entry and silently no-ops."""
    manager, ws = _make_manager()
    ticks = []
    on_tick = ticks.append
    manager.subscribe("CRUDEOIL", "MCX", "LTP", on_tick=on_tick)
    assert len(ws.listeners) == 1

    manager.unsubscribe("CRUDEOIL", "MCX", on_tick=on_tick)
    assert len(ws.listeners) == 0
