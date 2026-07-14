"""create_composers()/create_composers_from_infra() must not require a
caller-supplied risk_manager.

Regression guard: both functions build a default RiskManager via
``RiskManager(config=RiskConfig())`` when risk_manager=None, but
RiskManager.__init__ takes a required ``position_manager`` first
argument -- every caller that didn't pass risk_manager= explicitly (e.g.
scripts/sync_datalake.py's federated fetch, which only wants
MarketDataComposer) hit ``TypeError: RiskManager.__init__() missing 1
required positional argument: 'position_manager'``.
"""

from __future__ import annotations

from application.composer.factory import create_composers


def test_create_composers_with_no_gateways_does_not_raise():
    market_data, execution = create_composers([])
    assert market_data is not None
    assert execution is not None
