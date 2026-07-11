"""TOS-P6-003 options capability."""

from __future__ import annotations

from application.options import OptionsCapability


class _FakeGW:
    def option_chain(self, underlying, exchange="NSE", expiry=None):
        return {
            "underlying": underlying,
            "calls": [{"strike": 100}],
            "puts": [{"strike": 100}],
            "expiry": expiry,
        }

    def future_chain(self, underlying, exchange="NFO"):
        return [{"symbol": f"{underlying}FUT"}]


def test_options_capability_chain_and_payoff():
    cap = OptionsCapability(gateway=_FakeGW())
    chain = cap.chain("NIFTY")
    assert len(chain["calls"]) == 1
    assert cap.future_chain("NIFTY")
    payoff = cap.payoff_stub("NIFTY", 100.0)
    assert payoff["payoffs"]
