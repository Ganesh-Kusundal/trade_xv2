"""Shared alternate-key generator for broker instrument resolvers.

Single source of truth for symbol alias generation so Dhan and Upstox
resolvers cannot drift (zero-parity rule).
"""

from __future__ import annotations

import logging
from typing import Any

from domain.symbols import normalize_symbol

logger = logging.getLogger(__name__)


def generate_alternate_keys(
    symbol: str,
    inst_type: str | Any,
    expiry: str | None,
    strike: Any,
    option_type: Any,
    underlying: str | None,
    canonical_symbol: str | None,
    sm_symbol_name: str | None = None,
) -> list[str]:
    """Generate lookup aliases for a trading instrument.

    Covers primary/canonical/stripped forms, optional SM_SYMBOL_NAME,
    and spaced/compact/weekly option + future variants.
    """
    keys: list[str] = []

    sym_up = normalize_symbol(symbol)
    keys.append(sym_up)

    if canonical_symbol:
        canon_up = normalize_symbol(canonical_symbol)
        keys.append(canon_up)
        if canon_up.endswith(" CALL"):
            keys.append(canon_up[:-5] + " CE")
        elif canon_up.endswith(" PUT"):
            keys.append(canon_up[:-4] + " PE")

    stripped = sym_up.replace(" ", "").replace("-", "").replace("_", "")
    keys.append(stripped)

    if sm_symbol_name:
        keys.append(normalize_symbol(sm_symbol_name))

    type_str = str(inst_type).upper()
    is_option = "OPT" in type_str or "OPTION" in type_str
    is_future = "FUT" in type_str or "FUTURE" in type_str

    if (is_option or is_future) and expiry and underlying:
        try:
            from datetime import datetime

            dt = datetime.strptime(expiry[:10], "%Y-%m-%d")
            dd = dt.strftime("%d")
            dd_strip = str(int(dd))
            mmm = dt.strftime("%b").upper()
            yy = dt.strftime("%y")
            yyyy = dt.strftime("%Y")

            month_chars = ["1", "2", "3", "4", "5", "6", "7", "8", "9", "O", "N", "D"]
            month_char = month_chars[dt.month - 1]

            und_up = normalize_symbol(underlying)

            if is_option:
                opt_str = str(option_type).upper()
                ce_pe = "CE" if "CALL" in opt_str or "CE" in opt_str or "C" in opt_str else "PE"
                call_put = "CALL" if ce_pe == "CE" else "PUT"

                strike_str = ""
                if strike is not None:
                    try:
                        st_val = float(strike)
                        strike_str = str(int(st_val)) if st_val % 1 == 0 else str(st_val)
                    except (ValueError, TypeError):
                        strike_str = str(strike)

                keys.append(f"{und_up} {dd} {mmm} {yy} {strike_str} {ce_pe}")
                keys.append(f"{und_up} {dd_strip} {mmm} {yy} {strike_str} {ce_pe}")
                keys.append(f"{und_up} {dd} {mmm} {yyyy} {strike_str} {ce_pe}")
                keys.append(f"{und_up} {dd_strip} {mmm} {yyyy} {strike_str} {ce_pe}")
                keys.append(f"{und_up} {dd} {mmm} {strike_str} {ce_pe}")
                keys.append(f"{und_up} {dd_strip} {mmm} {strike_str} {ce_pe}")

                keys.append(f"{und_up} {dd} {mmm} {strike_str} {call_put}")
                keys.append(f"{und_up} {dd_strip} {mmm} {strike_str} {call_put}")

                keys.append(f"{und_up}{dd}{mmm}{yy}{strike_str}{ce_pe}")
                keys.append(f"{und_up}{dd_strip}{mmm}{yy}{strike_str}{ce_pe}")
                keys.append(f"{und_up}{dd}{mmm}{yyyy}{strike_str}{ce_pe}")
                keys.append(f"{und_up}{dd_strip}{mmm}{yyyy}{strike_str}{ce_pe}")
                keys.append(f"{und_up}{dd}{mmm}{strike_str}{ce_pe}")
                keys.append(f"{und_up}{dd_strip}{mmm}{strike_str}{ce_pe}")

                keys.append(f"{und_up}{yy}{month_char}{dd}{strike_str}{ce_pe}")
                keys.append(f"{und_up}{yy}{month_char}{dd_strip}{strike_str}{ce_pe}")

            elif is_future:
                keys.append(f"{und_up} {mmm} FUT")
                keys.append(f"{und_up} {yy} {mmm} FUT")
                keys.append(f"{und_up} {yyyy} {mmm} FUT")
                keys.append(f"{und_up} {dd} {mmm} FUT")
                keys.append(f"{und_up} FUT")

                keys.append(f"{und_up}{mmm}FUT")
                keys.append(f"{und_up}{yy}{mmm}FUT")
                keys.append(f"{und_up}{yyyy}{mmm}FUT")
                keys.append(f"{und_up}{dd}{mmm}FUT")
                keys.append(f"{und_up}FUT")
        except Exception as exc:
            logger.debug("alternate_key_generation_failed: %s", exc)

    res: list[str] = []
    seen: set[str] = set()
    for k in keys:
        k_clean = normalize_symbol(k)
        if k_clean and k_clean not in seen:
            seen.add(k_clean)
            res.append(k_clean)
    return res
