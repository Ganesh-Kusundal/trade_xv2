"""Backward-compat shim — moved to config.secrets_manager.

Canonical location: config/secrets_manager.py
All new code should import from config.secrets_manager instead.
"""
from config.secrets_manager import *  # noqa: F403
