import pytest
from decimal import Decimal
from application.oms import PositionManager, RiskConfig, RiskManager


@pytest.fixture
def position_manager():
    return PositionManager()


@pytest.fixture
def risk_config():
    return RiskConfig()


@pytest.fixture
def capital_provider():
    return lambda: Decimal("1000000")


@pytest.fixture
def risk_manager(position_manager, risk_config, capital_provider):
    return RiskManager(position_manager, risk_config, capital_fn=capital_provider)
