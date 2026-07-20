"""Certification tests need composition-root wiring (session + historical)."""

from __future__ import annotations

import pytest


@pytest.fixture(scope="session", autouse=True)
def _wire_composition_for_certification() -> None:
    from runtime.composition import wire_domain_port_sinks
    from runtime.session_opener import set_session_opener
    from tradex.session import open_session

    wire_domain_port_sinks()
    set_session_opener(open_session)
