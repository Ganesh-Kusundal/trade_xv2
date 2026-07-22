"""Session recording opt-in helper (TRADEX_SESSION_RECORD=1).

Extracted from ``tradex.session`` so the composition root stays small and this
helper has no dependency back on ``session`` (no circular imports).
"""

from __future__ import annotations

import logging
import os
from typing import Any

logger = logging.getLogger(__name__)


def is_enabled() -> bool:
    """Opt-in SessionRecording via ``TRADEX_SESSION_RECORD=1`` (default off)."""
    raw = (os.environ.get("TRADEX_SESSION_RECORD") or "").strip().lower()
    return raw in {"1", "true", "yes", "on"}


def maybe_start(
    session: Any,
    event_bus: Any | None,
    *,
    session_id: str | None = None,
) -> None:
    """Start SessionRecorder when enabled and an event bus is available.

    Non-critical: any failure is logged and swallowed so connect never fails
    because of recording (Blueprint Part 3 §4.3 SessionRecording).
    """
    if not is_enabled():
        return
    bus = event_bus if event_bus is not None else getattr(session, "event_bus", None)
    if bus is None:
        logger.debug("session_recorder_skipped_no_event_bus")
        return
    try:
        from infrastructure.observability.session_recorder import (
            SessionRecorder,
            resolve_session_recording_dir,
        )

        recorder = SessionRecorder(
            bus,
            session_id=session_id,
            output_dir=resolve_session_recording_dir(),
        )
        recorder.start()
        session._session_recorder = recorder
    except Exception:
        logger.warning("session_recorder_start_failed", exc_info=True)
