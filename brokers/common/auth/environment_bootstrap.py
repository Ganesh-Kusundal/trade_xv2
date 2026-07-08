"""Central environment bootstrap for all process entry points.

Re-exports from ``infrastructure.io.environment_bootstrap`` for backward
compatibility. New code should import from
``infrastructure.io.environment_bootstrap`` directly.
"""

from infrastructure.io.environment_bootstrap import bootstrap_environment

__all__ = ["bootstrap_environment"]
