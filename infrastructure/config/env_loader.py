"""Shared .env file loader — single implementation used by all broker factories.

Re-exports from ``infrastructure.io.environment_bootstrap`` for backward
compatibility. New code should import from
``infrastructure.io.environment_bootstrap`` directly.
"""

from infrastructure.io.environment_bootstrap import load_env_file

__all__ = ["load_env_file"]
