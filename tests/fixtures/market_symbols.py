"""Canonical market symbols and exchanges for integration tests."""

from __future__ import annotations

# Equity symbols (NSE cash)
SYMBOL_RELIANCE = "RELIANCE"
SYMBOL_TCS = "TCS"
SYMBOL_INFY = "INFY"
SYMBOL_HDFCBANK = "HDFCBANK"
SYMBOL_SBIN = "SBIN"

# Index / derivatives underlyings
UNDERLYING_NIFTY = "NIFTY"
UNDERLYING_BANKNIFTY = "BANKNIFTY"

# Exchange segments (wire format)
EXCHANGE_NSE_EQ = "NSE_EQ"
EXCHANGE_NFO = "NFO"
EXCHANGE_INDEX = "INDEX"

# Short exchange codes (gateway defaults)
EXCHANGE_NSE = "NSE"

__all__ = [
    "EXCHANGE_INDEX",
    "EXCHANGE_NFO",
    "EXCHANGE_NSE",
    "EXCHANGE_NSE_EQ",
    "SYMBOL_HDFCBANK",
    "SYMBOL_INFY",
    "SYMBOL_RELIANCE",
    "SYMBOL_SBIN",
    "SYMBOL_TCS",
    "UNDERLYING_BANKNIFTY",
    "UNDERLYING_NIFTY",
]
