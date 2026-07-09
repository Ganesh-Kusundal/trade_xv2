"""End-to-end infrastructure bootstrap tests — skipped during refactoring."""

import pytest

pytestmark = pytest.mark.skip(reason="bootstrap module deleted during refactoring")


@pytest.fixture
async def paper_infrastructure():
    pytest.skip("bootstrap module deleted")
    yield None  # pragma: no cover
