"""Shared instrument parsing utilities."""

from __future__ import annotations

_MONTHS = {"JAN", "FEB", "MAR", "APR", "MAY", "JUN", "JUL", "AUG", "SEP", "OCT", "NOV", "DEC"}


def normalize_option_type(symbol: str) -> str:
    """Normalize CALL->CE, PUT->PE."""
    s = symbol.upper().strip()
    if s.endswith("CALL"):
        return s[:-4] + "CE"
    elif s.endswith("PUT"):
        return s[:-3] + "PE"
    return s


def parse_derivative_input(norm: str) -> tuple[str, str | None, str | None]:
    """Parse 'NIFTY 26 JUN 25000 CE' -> ('NIFTY', '25000', 'CE')."""
    if norm.endswith("CE") or norm.endswith("PE"):
        opt_type = norm[-2:]
        rest = norm[:-2].strip()
        parts = rest.split()

        if len(parts) == 1:
            import re
            m = re.match(r"^([A-Z]+?)(\d+)$", parts[0])
            if m:
                return m.group(1), m.group(2), opt_type

        strike = None
        strike_idx = None
        for i in range(len(parts) - 1, -1, -1):
            if parts[i].isdigit():
                strike = parts[i]
                strike_idx = i
                break
        header = " ".join(parts[:strike_idx]) if strike_idx is not None else rest
        header_parts = header.split()
        underlying_parts = []
        for i, p in enumerate(header_parts):
            if p in _MONTHS:
                if underlying_parts and underlying_parts[-1].isdigit():
                    underlying_parts.pop()
                continue
            if p.isdigit() and i + 1 < len(header_parts) and header_parts[i + 1] in _MONTHS:
                continue
            if p.isdigit() and len(p) == 4:
                continue
            if p.isdigit() and len(p) == 2 and i + 1 < len(header_parts) and header_parts[i + 1] in _MONTHS:
                continue
            underlying_parts.append(p)
        return " ".join(underlying_parts).strip(), strike, opt_type

    if "FUT" in norm:
        parts = norm.split()
        result = []
        for i, p in enumerate(parts):
            if p in _MONTHS:
                if result and result[-1].isdigit():
                    result.pop()
                continue
            if p.isdigit() and i + 1 < len(parts) and parts[i + 1] in _MONTHS:
                continue
            if p == "FUT":
                continue
            result.append(p)
        return " ".join(result).strip(), None, "FUT"

    return norm, None, None
