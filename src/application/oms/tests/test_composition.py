"""ENG-011 composition helpers."""

from __future__ import annotations

import pytest

from application.oms.composition import require_process_oms
from application.oms.process_context import reset_oms_context


def test_require_process_oms_raises_without_registration():
    reset_oms_context()
    with pytest.raises(RuntimeError, match="ENG-011"):
        require_process_oms(for_broker="dhan")
