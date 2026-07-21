"""Brokers services — shared core for SDK and composition-root consumers.

New code should import from the focused submodule directly::

    from brokers.services.capabilities import format_session_capabilities
    from brokers.services.serialization import safe_serialize
    from brokers.services.market_data import get_quote
"""

from __future__ import annotations

from brokers.services._session import (  # noqa: F401
    _borrow_session,
    _open,
    extensions_from_session,
    run_connect,
    status_from_session,
)
from brokers.services.capabilities import (  # noqa: F401
    _cap_value,
    _caps_to_dict,
    _session_gateway,
    format_session_capabilities,
    get_capabilities,
)
from brokers.services.instrument_lookup import (  # noqa: F401
    lookup_instrument,
    lookup_security,
    lookup_symbol,
)
from brokers.services.market_data import (  # noqa: F401
    get_depth,
    get_depth30,
    get_history,
    get_history_batch,
    get_option_chain,
    get_quote,
    probe_depth_ws,
    run_subscribe_probe,
)
from brokers.services.orders import (  # noqa: F401
    cancel_order,
    get_news,
    list_forever_orders,
    list_super_orders,
    modify_order,
    place_order,
)
from brokers.services.portfolio import (  # noqa: F401
    get_funds,
    get_holdings,
    get_orders,
    get_positions,
)
from brokers.services.serialization import (  # noqa: F401
    safe_serialize,
)
