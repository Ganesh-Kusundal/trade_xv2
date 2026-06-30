"""Generated Python stub for Upstox V3 MarketDataFeed.proto.

If the real generated ``market_feed_pb2.py`` is present (built via
``python -m grpc_tools.protoc``), this module re-exports it. Otherwise it
falls back to a small dynamic-message shim so the rest of the package
imports cleanly.

To rebuild the real generated file::

    python -m grpc_tools.protoc -I brokers/upstox/websocket/proto \\
        --python_out=brokers/upstox/websocket/proto \\
        brokers/upstox/websocket/proto/MarketDataFeed.proto
"""

from __future__ import annotations

try:
    from .market_feed_pb2 import *  # type: ignore
except Exception:
    try:
        from market_feed_pb2 import *  # type: ignore
    except Exception:
        try:
            from google.protobuf import descriptor_pb2
            from google.protobuf import message as _message
            from google.protobuf import reflection as _reflection

            _FILE = descriptor_pb2.FileDescriptorProto()
            _FILE.name = "MarketDataFeed.proto"
            _FILE.package = "com.upstox.marketdatafeed"
            _FILE.syntax = "proto3"

            # ── LTPC ──
            _LTPC = _FILE.message_type.add()
            _LTPC.name = "LTPC"
            for name, ftype, num in [
                ("ltp", descriptor_pb2.FieldDescriptorProto.TYPE_DOUBLE, 1),
                ("ltt", descriptor_pb2.FieldDescriptorProto.TYPE_STRING, 2),
                ("ltq", descriptor_pb2.FieldDescriptorProto.TYPE_STRING, 3),
                ("cp", descriptor_pb2.FieldDescriptorProto.TYPE_DOUBLE, 4),
            ]:
                f = _LTPC.field.add()
                f.name = name
                f.type = ftype
                f.number = num

            # ── OHLC ──
            _OHLC = _FILE.message_type.add()
            _OHLC.name = "OHLC"
            for name, ftype, num in [
                ("interval", descriptor_pb2.FieldDescriptorProto.TYPE_STRING, 1),
                ("open", descriptor_pb2.FieldDescriptorProto.TYPE_DOUBLE, 2),
                ("high", descriptor_pb2.FieldDescriptorProto.TYPE_DOUBLE, 3),
                ("low", descriptor_pb2.FieldDescriptorProto.TYPE_DOUBLE, 4),
                ("close", descriptor_pb2.FieldDescriptorProto.TYPE_DOUBLE, 5),
                ("vol", descriptor_pb2.FieldDescriptorProto.TYPE_STRING, 6),
                ("ts", descriptor_pb2.FieldDescriptorProto.TYPE_STRING, 7),
            ]:
                f = _OHLC.field.add()
                f.name = name
                f.type = ftype
                f.number = num

            # ── MarketOHLC ──
            _MarketOHLC = _FILE.message_type.add()
            _MarketOHLC.name = "MarketOHLC"
            f = _MarketOHLC.field.add()
            f.name = "ohlc"
            f.type = descriptor_pb2.FieldDescriptorProto.TYPE_MESSAGE
            f.type_name = ".com.upstox.marketdatafeed.OHLC"
            f.number = 1
            f.label = descriptor_pb2.FieldDescriptorProto.LABEL_REPEATED

            # ── OptionGreeks ──
            _OptionGreeks = _FILE.message_type.add()
            _OptionGreeks.name = "OptionGreeks"
            for name, ftype, num in [
                ("delta", descriptor_pb2.FieldDescriptorProto.TYPE_DOUBLE, 1),
                ("theta", descriptor_pb2.FieldDescriptorProto.TYPE_DOUBLE, 2),
                ("gamma", descriptor_pb2.FieldDescriptorProto.TYPE_DOUBLE, 3),
                ("vega", descriptor_pb2.FieldDescriptorProto.TYPE_DOUBLE, 4),
                ("rho", descriptor_pb2.FieldDescriptorProto.TYPE_DOUBLE, 5),
            ]:
                f = _OptionGreeks.field.add()
                f.name = name
                f.type = ftype
                f.number = num

            # ── FirstDepth ──
            _FirstDepth = _FILE.message_type.add()
            _FirstDepth.name = "FirstDepth"
            for name, ftype, num in [
                ("bidQ", descriptor_pb2.FieldDescriptorProto.TYPE_STRING, 1),
                ("bidP", descriptor_pb2.FieldDescriptorProto.TYPE_DOUBLE, 2),
                ("askQ", descriptor_pb2.FieldDescriptorProto.TYPE_STRING, 3),
                ("askP", descriptor_pb2.FieldDescriptorProto.TYPE_DOUBLE, 4),
            ]:
                f = _FirstDepth.field.add()
                f.name = name
                f.type = ftype
                f.number = num

            # ── FirstLevelWithGreeks ──
            _FirstLevelWithGreeks = _FILE.message_type.add()
            _FirstLevelWithGreeks.name = "FirstLevelWithGreeks"
            for name, msg_name, num in [
                ("ltpc", "LTPC", 1),
                ("firstDepth", "FirstDepth", 2),
                ("optionGreeks", "OptionGreeks", 3),
            ]:
                f = _FirstLevelWithGreeks.field.add()
                f.name = name
                f.type = descriptor_pb2.FieldDescriptorProto.TYPE_MESSAGE
                f.type_name = f".com.upstox.marketdatafeed.{msg_name}"
                f.number = num
            f = _FirstLevelWithGreeks.field.add()
            f.name = "vtt"
            f.type = descriptor_pb2.FieldDescriptorProto.TYPE_STRING
            f.number = 4
            f = _FirstLevelWithGreeks.field.add()
            f.name = "oi"
            f.type = descriptor_pb2.FieldDescriptorProto.TYPE_INT64
            f.number = 5
            f = _FirstLevelWithGreeks.field.add()
            f.name = "iv"
            f.type = descriptor_pb2.FieldDescriptorProto.TYPE_DOUBLE
            f.number = 6

            # ── BidAskQuote ──
            _BidAskQuote = _FILE.message_type.add()
            _BidAskQuote.name = "BidAskQuote"
            for name, ftype, num in [
                ("bidQ", descriptor_pb2.FieldDescriptorProto.TYPE_STRING, 1),
                ("bidP", descriptor_pb2.FieldDescriptorProto.TYPE_DOUBLE, 2),
                ("askQ", descriptor_pb2.FieldDescriptorProto.TYPE_STRING, 3),
                ("askP", descriptor_pb2.FieldDescriptorProto.TYPE_DOUBLE, 4),
            ]:
                f = _BidAskQuote.field.add()
                f.name = name
                f.type = ftype
                f.number = num

            # ── MarketLevel ──
            _MarketLevel = _FILE.message_type.add()
            _MarketLevel.name = "MarketLevel"
            f = _MarketLevel.field.add()
            f.name = "bidAskQuote"
            f.type = descriptor_pb2.FieldDescriptorProto.TYPE_MESSAGE
            f.type_name = ".com.upstox.marketdatafeed.BidAskQuote"
            f.number = 1
            f.label = descriptor_pb2.FieldDescriptorProto.LABEL_REPEATED

            # ── IndexFeed ──
            _IndexFeed = _FILE.message_type.add()
            _IndexFeed.name = "IndexFeed"
            for name, msg_name, num in [
                ("ltpc", "LTPC", 1),
                ("marketOHLC", "MarketOHLC", 2),
            ]:
                f = _IndexFeed.field.add()
                f.name = name
                f.type = descriptor_pb2.FieldDescriptorProto.TYPE_MESSAGE
                f.type_name = f".com.upstox.marketdatafeed.{msg_name}"
                f.number = num

            # ── MarketFF ──
            _MarketFF = _FILE.message_type.add()
            _MarketFF.name = "MarketFF"
            for name, msg_name, num in [
                ("ltpc", "LTPC", 1),
                ("marketLevel", "MarketLevel", 2),
                ("optionGreeks", "OptionGreeks", 3),
                ("marketOHLC", "MarketOHLC", 4),
            ]:
                f = _MarketFF.field.add()
                f.name = name
                f.type = descriptor_pb2.FieldDescriptorProto.TYPE_MESSAGE
                f.type_name = f".com.upstox.marketdatafeed.{msg_name}"
                f.number = num
            for name, ftype, num in [
                ("atp", descriptor_pb2.FieldDescriptorProto.TYPE_DOUBLE, 5),
                ("vtt", descriptor_pb2.FieldDescriptorProto.TYPE_STRING, 6),
                ("oi", descriptor_pb2.FieldDescriptorProto.TYPE_INT64, 7),
                ("iv", descriptor_pb2.FieldDescriptorProto.TYPE_DOUBLE, 8),
                ("tbq", descriptor_pb2.FieldDescriptorProto.TYPE_INT64, 9),
                ("tsq", descriptor_pb2.FieldDescriptorProto.TYPE_INT64, 10),
            ]:
                f = _MarketFF.field.add()
                f.name = name
                f.type = ftype
                f.number = num

            # ── FullFeed ──
            _FullFeed = _FILE.message_type.add()
            _FullFeed.name = "FullFeed"
            f = _FullFeed.field.add()
            f.name = "marketFF"
            f.type = descriptor_pb2.FieldDescriptorProto.TYPE_MESSAGE
            f.type_name = ".com.upstox.marketdatafeed.MarketFF"
            f.number = 1

            # ── Quote ──
            _Quote = _FILE.message_type.add()
            _Quote.name = "Quote"
            for name, msg_name, num in [
                ("ltpc", "LTPC", 2),
                ("market_level", "MarketLevel", 3),
                ("market_ohlc", "MarketOHLC", 4),
                ("option_greeks", "OptionGreeks", 5),
                ("first_level_with_greeks", "FirstLevelWithGreeks", 6),
            ]:
                f = _Quote.field.add()
                f.name = name
                f.type = descriptor_pb2.FieldDescriptorProto.TYPE_MESSAGE
                f.type_name = f".com.upstox.marketdatafeed.{msg_name}"
                f.number = num
            f = _Quote.field.add()
            f.name = "instrument_key"
            f.type = descriptor_pb2.FieldDescriptorProto.TYPE_STRING
            f.number = 1

            # ── Feed ──
            _Feed = _FILE.message_type.add()
            _Feed.name = "Feed"
            for name, msg_name, num in [
                ("ltpc", "LTPC", 1),
                ("first_level_with_greeks", "FirstLevelWithGreeks", 2),
                ("fullFeed", "FullFeed", 3),
                ("indexFeed", "IndexFeed", 4),
            ]:
                f = _Feed.field.add()
                f.name = name
                f.type = descriptor_pb2.FieldDescriptorProto.TYPE_MESSAGE
                f.type_name = f".com.upstox.marketdatafeed.{msg_name}"
                f.number = num

            _pool = _message.Default()
            _pool.Add(_FILE)
            _factory = _reflection.MakeGeneratedMessageClass
            LTPC = _factory(_LTPC, _pool)
            OHLC = _factory(_OHLC, _pool)
            MarketOHLC = _factory(_MarketOHLC, _pool)
            OptionGreeks = _factory(_OptionGreeks, _pool)
            FirstDepth = _factory(_FirstDepth, _pool)
            FirstLevelWithGreeks = _factory(_FirstLevelWithGreeks, _pool)
            BidAskQuote = _factory(_BidAskQuote, _pool)
            MarketLevel = _factory(_MarketLevel, _pool)
            IndexFeed = _factory(_IndexFeed, _pool)
            MarketFF = _factory(_MarketFF, _pool)
            FullFeed = _factory(_FullFeed, _pool)
            Quote = _factory(_Quote, _pool)
            Feed = _factory(_Feed, _pool)
        except Exception:
            LTPC = None
            OHLC = None
            MarketOHLC = None
            OptionGreeks = None
            FirstDepth = None
            FirstLevelWithGreeks = None
            BidAskQuote = None
            MarketLevel = None
            IndexFeed = None
            MarketFF = None
            FullFeed = None
            Quote = None
            Feed = None


__all__ = [
    "LTPC",
    "OHLC",
    "BidAskQuote",
    "Feed",
    "FirstDepth",
    "FirstLevelWithGreeks",
    "FullFeed",
    "IndexFeed",
    "MarketFF",
    "MarketLevel",
    "MarketOHLC",
    "OptionGreeks",
    "Quote",
]
