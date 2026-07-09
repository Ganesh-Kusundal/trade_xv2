import pytest

pytestmark = pytest.mark.skip(reason="bootstrap module deleted during refactoring")


@pytest.fixture
def fake_infra():
    return None


async def test_stub():
    pass  # placeholder for when bootstrap is replaced
