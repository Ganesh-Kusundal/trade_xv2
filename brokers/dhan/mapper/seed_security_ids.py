"""Verified Dhan v2 security ID mappings.

Source of truth: ``api-scrip-master-*.csv`` published daily by Dhan HQ.

This module is the **single, audited registry** of security IDs for instruments
that the platform can resolve before (or without) the full Dhan instrument
catalog being downloaded.  Every entry here has been cross-checked against the
official Dhan CSV.  If the CSV ever disagrees with this file, the CSV wins —
but the values here are the seed-of-record for the rest of the system.

Why a separate file?
--------------------
1. ``brokers.common.core.instruments.InstrumentRegistry`` stores the same data
   for the canonical engine.
2. ``brokers.dhan.mapper.instruments.DhanInstrumentResolver`` keeps a parallel
   seed table for the legacy resolver code path.
3. We want a *single* Python source we can both files ``import`` from so a
   drift between the two is impossible.

Whenever the Dhan master is re-audited, only this file needs to change.  The
``TestDhanSeedSecurityIds`` class pins the values to guarantee regressions are
caught by CI.
"""

from __future__ import annotations

# (canonical_symbol, exchange) -> security_id
# All values verified against /Users/apple/Downloads/Trade_J/runtime-dev/instruments/api-scrip-master-2026-06-10.csv
DHAN_SEED_SECURITY_IDS: dict[tuple[str, str], str] = {
    # ─── Equity (NSE) — verified from NSE/E rows in Dhan v2 master ──────────
    ("ADANIENT", "NSE"): "25",
    ("ADANIPORTS", "NSE"): "15083",
    ("APOLLOHOSP", "NSE"): "157",
    ("ASIANPAINT", "NSE"): "236",
    ("AXISBANK", "NSE"): "5900",
    ("BAJAJ-AUTO", "NSE"): "16669",
    ("BAJFINANCE", "NSE"): "317",
    ("BAJAJFINSV", "NSE"): "16675",
    ("BPCL", "NSE"): "526",
    ("BHARTIARTL", "NSE"): "10604",
    ("BRITANNIA", "NSE"): "547",
    ("CIPLA", "NSE"): "694",
    ("COALINDIA", "NSE"): "20374",
    ("DIVISLAB", "NSE"): "10940",
    ("DRREDDY", "NSE"): "881",
    ("EICHERMOT", "NSE"): "910",
    ("GRASIM", "NSE"): "1232",
    ("HCLTECH", "NSE"): "7229",
    ("HDFCBANK", "NSE"): "1333",
    ("HDFCLIFE", "NSE"): "467",
    ("HEROMOTOCO", "NSE"): "1348",
    ("HINDALCO", "NSE"): "1363",
    ("HINDUNILVR", "NSE"): "1394",
    ("ICICIBANK", "NSE"): "4963",
    ("INDUSINDBK", "NSE"): "5258",
    ("INFY", "NSE"): "1594",
    ("ITC", "NSE"): "1660",
    ("JSWSTEEL", "NSE"): "11723",
    ("KOTAKBANK", "NSE"): "1922",
    ("LT", "NSE"): "11483",
    ("M&M", "NSE"): "2031",
    ("MARUTI", "NSE"): "10999",
    ("NESTLEIND", "NSE"): "17963",
    ("NTPC", "NSE"): "11630",
    ("ONGC", "NSE"): "2475",
    ("POWERGRID", "NSE"): "14977",
    ("RELIANCE", "NSE"): "2885",
    ("SBILIFE", "NSE"): "21808",
    ("SBIN", "NSE"): "3045",
    ("SUNPHARMA", "NSE"): "3351",
    ("TCS", "NSE"): "11536",
    ("TATACONSUM", "NSE"): "3432",
    ("TATASTEEL", "NSE"): "3499",
    ("TECHM", "NSE"): "13538",
    ("TITAN", "NSE"): "3506",
    ("ULTRACEMCO", "NSE"): "11532",
    ("UPL", "NSE"): "11287",
    ("WIPRO", "NSE"): "3787",
    ("HEG", "NSE"): "1336",
    # ─── Indices (NSE Index / IDX_I segment) ────────────────────────────────
    ("NIFTY", "IDX"): "13",
    ("NIFTY", "IDX_I"): "13",
    ("BANKNIFTY", "IDX"): "25",
    ("BANKNIFTY", "IDX_I"): "25",
    ("FINNIFTY", "IDX"): "27",
    ("FINNIFTY", "IDX_I"): "27",
    ("MIDCPNIFTY", "IDX"): "442",
    ("MIDCPNIFTY", "IDX_I"): "442",
    ("SENSEX", "IDX"): "51",
    ("SENSEX", "IDX_I"): "51",
    ("NIFTYNXT50", "IDX"): "38",
    ("NIFTYNXT50", "IDX_I"): "38",
    # ─── BSE equity (verified from BSE/E rows) ──────────────────────────────
    ("TCS", "BSE"): "532540",
    ("RELIANCE", "BSE"): "500325",
    ("HDFCBANK", "BSE"): "500180",
    ("SBIN", "BSE"): "500112",
    ("INFY", "BSE"): "500209",
}


# Canonical well-known security IDs used in tests / smoke checks
RELIANCE_NSE_SID = "2885"
TCS_NSE_SID = "11536"
SBIN_NSE_SID = "3045"
INFY_NSE_SID = "1594"
HDFCBANK_NSE_SID = "1333"
NIFTY_IDX_SID = "13"
BANKNIFTY_IDX_SID = "25"
FINNIFTY_IDX_SID = "27"
NIFTYNXT50_IDX_SID = "38"
MIDCPNIFTY_IDX_SID = "442"
SENSEX_IDX_SID = "51"
