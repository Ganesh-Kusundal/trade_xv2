"""Tests for api.routers.live.serialize — domain object serialization."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from interface.api.routers.live.serialize import serialize_value


class TestSerializeValue:
    def test_none(self):
        assert serialize_value(None) is None

    def test_decimal(self):
        assert serialize_value(Decimal("123.45")) == "123.45"

    def test_plain_types_passthrough(self):
        assert serialize_value(42) == 42
        assert serialize_value("hello") == "hello"
        assert serialize_value(True) is True

    def test_list(self):
        result = serialize_value([Decimal("1"), Decimal("2")])
        assert result == ["1", "2"]

    def test_dict(self):
        result = serialize_value({"price": Decimal("99.9"), "qty": 10})
        assert result == {"price": "99.9", "qty": 10}

    def test_nested_structure(self):
        data = {"items": [Decimal("1.5"), {"nested": Decimal("2.5")}]}
        result = serialize_value(data)
        assert result == {"items": ["1.5", {"nested": "2.5"}]}

    def test_dataclass(self):
        @dataclass
        class Point:
            x: Decimal
            y: Decimal

        result = serialize_value(Point(Decimal("1.0"), Decimal("2.0")))
        assert result == {"x": "1.0", "y": "2.0"}

    def test_to_dict_protocol(self):
        class Custom:
            def to_dict(self):
                return {"value": Decimal("42")}

        result = serialize_value(Custom())
        assert result == {"value": "42"}

    def test_empty_containers(self):
        assert serialize_value([]) == []
        assert serialize_value({}) == {}

    def test_tuple(self):
        result = serialize_value((Decimal("1"), Decimal("2")))
        assert result == ["1", "2"]
