"""TDD tests for GatewayResult — Trade_J-inspired result type with metadata."""

from decimal import Decimal

from brokers.common.core.result import GatewayResult, ResultMetadata


class TestResultMetadata:
    def test_default(self):
        m = ResultMetadata()
        assert m.source == ""
        assert m.latency_ms == 0.0
        assert m.cached is False

    def test_with_values(self):
        m = ResultMetadata(source="dhan", latency_ms=45.2, cached=False)
        assert m.source == "dhan"
        assert m.latency_ms == 45.2

    def test_cached(self):
        m = ResultMetadata(cached=True, cache_hit=True)
        assert m.cached is True
        assert m.cache_hit is True


class TestGatewayResultSuccess:
    def test_success_result(self):
        result: GatewayResult[str] = GatewayResult.success("hello")
        assert result.is_success is True
        assert result.is_failure is False
        assert result.value == "hello"
        assert result.error is None

    def test_success_with_metadata(self):
        meta = ResultMetadata(source="paper")
        result = GatewayResult.success(42, metadata=meta)
        assert result.value == 42
        assert result.metadata.source == "paper"

    def test_success_of_different_types(self):
        assert GatewayResult.success(123).value == 123
        assert GatewayResult.success("abc").value == "abc"
        assert GatewayResult.success(Decimal("99.5")).value == Decimal("99.5")
        assert GatewayResult.success([1, 2, 3]).value == [1, 2, 3]


class TestGatewayResultFailure:
    def test_failure_with_message(self):
        result: GatewayResult[str] = GatewayResult.failure("something went wrong")
        assert result.is_success is False
        assert result.is_failure is True
        assert result.error == "something went wrong"
        assert result.value is None

    def test_failure_with_exception(self):
        exc = ValueError("invalid order")
        result = GatewayResult.failure(exc)
        assert result.is_failure is True
        assert "invalid order" in str(result.error)

    def test_failure_with_metadata(self):
        meta = ResultMetadata(source="dhan", latency_ms=100)
        result = GatewayResult.failure("rate limited", metadata=meta)
        assert result.metadata.source == "dhan"
        assert result.metadata.latency_ms == 100


class TestGatewayResultCombinators:
    def test_map_on_success(self):
        result = GatewayResult.success(10).map(lambda x: x * 2)
        assert result.value == 20

    def test_map_on_failure(self):
        result = GatewayResult.failure("error").map(lambda x: x * 2)
        assert result.is_failure is True
        assert result.error == "error"

    def test_flat_map_on_success(self):
        result = GatewayResult.success(5).flat_map(lambda x: GatewayResult.success(x * 3))
        assert result.value == 15

    def test_flat_map_on_failure(self):
        result = GatewayResult.failure("fail").flat_map(lambda x: GatewayResult.success(x))
        assert result.is_failure is True

    def test_recover_on_failure(self):
        result = GatewayResult.failure("error").recover(lambda err: "default")
        assert result.value == "default"
        assert result.is_success is True

    def test_recover_on_success(self):
        result = GatewayResult.success("ok").recover(lambda err: "default")
        assert result.value == "ok"

    def test_get_or_else_on_success(self):
        assert GatewayResult.success(42).get_or_else(0) == 42

    def test_get_or_else_on_failure(self):
        assert GatewayResult.failure("error").get_or_else(0) == 0


class TestGatewayResultChaining:
    def test_chain_of_transforms(self):
        result = GatewayResult.success(10).map(lambda x: x + 5).map(lambda x: x * 2)
        assert result.value == 30

    def test_pipeline_with_failure(self):
        result = (
            GatewayResult.success(10)
            .map(lambda x: x + 5)
            .flat_map(lambda x: GatewayResult.failure(f"failed at {x}"))
            .map(lambda x: x * 2)  # should not execute
        )
        assert result.is_failure is True
        assert "failed at 15" in str(result.error)


class TestGatewayResultUtility:
    def test_str_success(self):
        s = str(GatewayResult.success(42))
        assert "Success" in s
        assert "42" in s

    def test_str_failure(self):
        s = str(GatewayResult.failure("error"))
        assert "Failure" in s
        assert "error" in s

    def test_bool_success(self):
        assert bool(GatewayResult.success(1)) is True

    def test_bool_failure(self):
        assert bool(GatewayResult.failure("err")) is False
