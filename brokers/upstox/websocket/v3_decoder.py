"""Upstox V3 binary frame decoder.

The V3 server pushes Protobuf-encoded binary frames. Each frame has a
1-byte type prefix and 2-byte big-endian length, then a Protobuf payload.

Mirrors Trade_J ``UpstoxBinaryParser`` / ``UpstoxMarketInfoParser``.
"""

from __future__ import annotations

import struct
from dataclasses import dataclass, field
from typing import Any

FRAME_HEARTBEAT = 100
FRAME_TYPE_INDEX = 1
FRAME_TYPE_LIVE_FEED = 2


@dataclass
class ParsedFeedFrame:
    type: int
    raw: bytes
    payload: dict[str, Any] = field(default_factory=dict)


class UpstoxV3Decoder:
    """Parse Upstox V3 binary feed frames into plain dicts."""

    def parse(self, raw: bytes) -> ParsedFeedFrame | None:
        if not raw or len(raw) < 3:
            return None
        frame_type = raw[0]
        (length,) = struct.unpack(">H", raw[1:3])
        if len(raw) < 3 + length:
            raise ValueError("Truncated Upstox V3 frame")
        payload_bytes = bytes(raw[3 : 3 + length])
        if frame_type == FRAME_HEARTBEAT:
            return ParsedFeedFrame(type=frame_type, raw=raw, payload={})
        try:
            from .proto.market_feed_pb2 import Feed

            feed = Feed()
            feed.ParseFromString(payload_bytes)
            payload = self._feed_to_dict(feed)
        except Exception:
            payload = {"raw_size": length}
        return ParsedFeedFrame(type=frame_type, raw=raw, payload=payload)

    @staticmethod
    def _feed_to_dict(feed: Any) -> dict[str, Any]:
        out: dict[str, Any] = {}
        if feed.HasField("ltpc"):
            lt = feed.ltpc
            out["ltpc"] = {"ltp": lt.ltp, "ltt": lt.ltt, "ltq": lt.ltq, "cp": lt.cp}
        if feed.HasField("first_level_with_greeks"):
            flg = feed.first_level_with_greeks
            out["first_level_with_greeks"] = {
                "ltpc": {"ltp": flg.ltpc.ltp, "ltq": flg.ltpc.ltq, "cp": flg.ltpc.cp},
                "first_depth": {
                    "bidQ": flg.firstDepth.bidQ,
                    "bidP": flg.firstDepth.bidP,
                    "askQ": flg.firstDepth.askQ,
                    "askP": flg.firstDepth.askP,
                },
                "vtt": flg.vtt,
                "oi": flg.oi,
                "iv": flg.iv,
                "optionGreeks": {
                    "delta": flg.optionGreeks.delta,
                    "theta": flg.optionGreeks.theta,
                    "gamma": flg.optionGreeks.gamma,
                    "vega": flg.optionGreeks.vega,
                    "rho": flg.optionGreeks.rho,
                },
            }
        if feed.HasField("fullFeed"):
            ff = feed.fullFeed
            if ff.HasField("marketFF"):
                mf = ff.marketFF
                out["full_feed"] = {
                    "ltpc": {
                        "ltp": mf.ltpc.ltp,
                        "cp": mf.ltpc.cp,
                        "ltt": mf.ltpc.ltt,
                        "ltq": mf.ltpc.ltq,
                    },
                    "atp": mf.atp,
                    "vtt": mf.vtt,
                    "oi": mf.oi,
                    "iv": mf.iv,
                    "tbq": mf.tbq,
                    "tsq": mf.tsq,
                    "optionGreeks": {
                        "delta": mf.optionGreeks.delta,
                        "theta": mf.optionGreeks.theta,
                        "gamma": mf.optionGreeks.gamma,
                        "vega": mf.optionGreeks.vega,
                        "rho": mf.optionGreeks.rho,
                    },
                    "marketOHLC": [
                        {
                            "interval": o.interval,
                            "open": o.open,
                            "high": o.high,
                            "low": o.low,
                            "close": o.close,
                            "vol": o.vol,
                            "ts": o.ts,
                        }
                        for o in mf.marketOHLC.ohlc
                    ],
                    "marketLevel": {
                        "bidAskQuote": [
                            {
                                "bidQ": b.bidQ,
                                "bidP": b.bidP,
                                "askQ": b.askQ,
                                "askP": b.askP,
                            }
                            for b in mf.marketLevel.bidAskQuote
                        ]
                    },
                }
        if feed.HasField("indexFeed"):
            idx = feed.indexFeed
            out["index_feed"] = {
                "ltpc": {"ltp": idx.ltpc.ltp, "cp": idx.ltpc.cp},
                "marketOHLC": [
                    {
                        "interval": o.interval,
                        "open": o.open,
                        "high": o.high,
                        "low": o.low,
                        "close": o.close,
                        "vol": o.vol,
                        "ts": o.ts,
                    }
                    for o in idx.marketOHLC.ohlc
                ],
            }
        return out
