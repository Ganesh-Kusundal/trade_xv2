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

            _LTPC = _FILE.message_type.add()
            _LTPC.name = "LTPC"
            _field = _LTPC.field.add()
            _field.name = "ltp"
            _field.type = descriptor_pb2.FieldDescriptorProto.TYPE_DOUBLE
            _field.number = 1
            _field = _LTPC.field.add()
            _field.name = "ltt"
            _field.type = descriptor_pb2.FieldDescriptorProto.TYPE_STRING
            _field.number = 2
            _field = _LTPC.field.add()
            _field.name = "ltq"
            _field.type = descriptor_pb2.FieldDescriptorProto.TYPE_STRING
            _field.number = 3
            _field = _LTPC.field.add()
            _field.name = "cp"
            _field.type = descriptor_pb2.FieldDescriptorProto.TYPE_DOUBLE
            _field.number = 4

            _OHLC = _FILE.message_type.add()
            _OHLC.name = "OHLC"
            _field = _OHLC.field.add()
            _field.name = "interval"
            _field.type = descriptor_pb2.FieldDescriptorProto.TYPE_STRING
            _field.number = 1
            _field = _OHLC.field.add()
            _field.name = "open"
            _field.type = descriptor_pb2.FieldDescriptorProto.TYPE_DOUBLE
            _field.number = 2
            _field = _OHLC.field.add()
            _field.name = "high"
            _field.type = descriptor_pb2.FieldDescriptorProto.TYPE_DOUBLE
            _field.number = 3
            _field = _OHLC.field.add()
            _field.name = "low"
            _field.type = descriptor_pb2.FieldDescriptorProto.TYPE_DOUBLE
            _field.number = 4
            _field = _OHLC.field.add()
            _field.name = "close"
            _field.type = descriptor_pb2.FieldDescriptorProto.TYPE_DOUBLE
            _field.number = 5
            _field = _OHLC.field.add()
            _field.name = "vol"
            _field.type = descriptor_pb2.FieldDescriptorProto.TYPE_STRING
            _field.number = 6
            _field = _OHLC.field.add()
            _field.name = "ts"
            _field.type = descriptor_pb2.FieldDescriptorProto.TYPE_STRING
            _field.number = 7

            _MarketOHLC = _FILE.message_type.add()
            _MarketOHLC.name = "MarketOHLC"
            _field = _MarketOHLC.field.add()
            _field.name = "ohlc"
            _field.type = descriptor_pb2.FieldDescriptorProto.TYPE_MESSAGE
            _field.type_name = ".com.upstox.marketdatafeed.OHLC"
            _field.number = 1
            _field.label = descriptor_pb2.FieldDescriptorProto.LABEL_REPEATED

            _Quote = _FILE.message_type.add()
            _Quote.name = "Quote"
            _field = _Quote.field.add()
            _field.name = "instrument_key"
            _field.type = descriptor_pb2.FieldDescriptorProto.TYPE_STRING
            _field.number = 1
            _field = _Quote.field.add()
            _field.name = "ltpc"
            _field.type = descriptor_pb2.FieldDescriptorProto.TYPE_MESSAGE
            _field.type_name = ".com.upstox.marketdatafeed.LTPC"
            _field.number = 2
            _field = _Quote.field.add()
            _field.name = "market_level"
            _field.type = descriptor_pb2.FieldDescriptorProto.TYPE_MESSAGE
            _field.type_name = ".com.upstox.marketdatafeed.MarketLevel"
            _field.number = 3
            _field = _Quote.field.add()
            _field.name = "market_ohlc"
            _field.type = descriptor_pb2.FieldDescriptorProto.TYPE_MESSAGE
            _field.type_name = ".com.upstox.marketdatafeed.MarketOHLC"
            _field.number = 4
            _field = _Quote.field.add()
            _field.name = "option_greeks"
            _field.type = descriptor_pb2.FieldDescriptorProto.TYPE_MESSAGE
            _field.type_name = ".com.upstox.marketdatafeed.OptionGreeks"
            _field.number = 5
            _field = _Quote.field.add()
            _field.name = "first_level_with_greeks"
            _field.type = descriptor_pb2.FieldDescriptorProto.TYPE_MESSAGE
            _field.type_name = ".com.upstox.marketdatafeed.FirstLevelWithGreeks"
            _field.number = 6

            _Feed = _FILE.message_type.add()
            _Feed.name = "Feed"
            _field = _Feed.field.add()
            _field.name = "ltpc"
            _field.type = descriptor_pb2.FieldDescriptorProto.TYPE_MESSAGE
            _field.type_name = ".com.upstox.marketdatafeed.LTPC"
            _field.number = 1
            _field = _Feed.field.add()
            _field.name = "first_level_with_greeks"
            _field.type = descriptor_pb2.FieldDescriptorProto.TYPE_MESSAGE
            _field.type_name = ".com.upstox.marketdatafeed.FirstLevelWithGreeks"
            _field.number = 2
            _field = _Feed.field.add()
            _field.name = "full_feed"
            _field.type = descriptor_pb2.FieldDescriptorProto.TYPE_MESSAGE
            _field.type_name = ".com.upstox.marketdatafeed.FullFeed"
            _field.number = 3
            _field = _Feed.field.add()
            _field.name = "index_feed"
            _field.type = descriptor_pb2.FieldDescriptorProto.TYPE_MESSAGE
            _field.type_name = ".com.upstox.marketdatafeed.IndexFeed"
            _field.number = 4

            _pool = _message.Default()
            _pool.Add(_FILE)
            factory = _reflection.MakeGeneratedMessageClass(_LTPC, _pool)
            LTPC = factory

            _factory = _reflection.MakeGeneratedMessageClass
            OHLC = _factory(_OHLC, _pool)
            MarketOHLC = _factory(_MarketOHLC, _pool)
            Quote = _factory(_Quote, _pool)
            Feed = _factory(_Feed, _pool)
        except Exception:
            LTPC = None
            OHLC = None
            MarketOHLC = None
            Quote = None
            Feed = None


__all__ = ["LTPC", "OHLC", "Feed", "MarketOHLC", "Quote"]
