"""REST delivery layer — re-exports FastAPI factory from ``api`` until Phase 5."""

from api.main import create_app

__all__ = ["create_app"]
