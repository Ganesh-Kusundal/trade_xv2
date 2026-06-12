"""broker — alias package for ``brokers``.

Allows the spec-required import::

    from broker import Gateway

    g = Gateway()
    g.ltp("TCS")
"""

from brokers import *  # noqa: F403
from brokers.gateway import Gateway

__all__ = ["Gateway"]
