"""Module-level API session holder (shared across routers)."""

from __future__ import annotations

from fastapi import HTTPException, status

from domain.universe import Session


class ApiSessionState:
    """Holds the wired :class:`Session` for API market routes."""

    _session: Session | None = None

    @classmethod
    def set(cls, session: Session) -> None:
        cls._session = session

    @classmethod
    def get(cls) -> Session:
        if cls._session is None:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Session not wired — call set_session() at startup",
            )
        return cls._session


def set_session(session: Session) -> None:
    ApiSessionState.set(session)


def get_session() -> Session:
    return ApiSessionState.get()
