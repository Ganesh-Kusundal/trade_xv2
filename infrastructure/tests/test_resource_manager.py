"""Tests for resource lifecycle managers."""

from __future__ import annotations

import asyncio
import threading
from unittest.mock import MagicMock

import pytest

from infrastructure.async_resource_manager import AsyncResourceManager
from infrastructure.health import HealthRegistry, HealthStatus
from infrastructure.resource_manager import ResourceManager


class TestResourceManager:
    """Tests for synchronous ResourceManager."""

    def test_register_and_get(self):
        rm = ResourceManager()
        resource = {"type": "pool"}
        rm.register("db_pool", resource)

        assert rm.get("db_pool") is resource
        assert rm.get("nonexistent") is None

    def test_register_duplicate_raises(self):
        rm = ResourceManager()
        rm.register("db_pool", {"type": "pool"})

        with pytest.raises(ValueError, match="already registered"):
            rm.register("db_pool", {"type": "other"})

    def test_unregister(self):
        rm = ResourceManager()
        rm.register("db_pool", {"type": "pool"})
        rm.unregister("db_pool")

        assert rm.get("db_pool") is None

    def test_unregister_nonexistent_is_noop(self):
        rm = ResourceManager()
        rm.unregister("nonexistent")

    def test_acquire_yields_resource(self):
        rm = ResourceManager()
        resource = {"type": "pool"}
        rm.register("db_pool", resource)

        with rm.acquire("db_pool") as r:
            assert r is resource

    def test_acquire_nonexistent_raises(self):
        rm = ResourceManager()
        with pytest.raises(KeyError, match="not registered"):
            with rm.acquire("nonexistent"):
                pass

    def test_cleanup_on_shutdown(self):
        rm = ResourceManager()
        cleanup_called = []

        rm.register("db_pool", {"type": "pool"}, lambda: cleanup_called.append("db_pool"))
        rm.register("http_client", {"type": "client"}, lambda: cleanup_called.append("http_client"))

        rm.shutdown_all()

        assert cleanup_called == ["http_client", "db_pool"]

    def test_reverse_order_cleanup(self):
        rm = ResourceManager()
        order = []

        rm.register("first", {"type": "1"}, lambda: order.append("first"))
        rm.register("second", {"type": "2"}, lambda: order.append("second"))
        rm.register("third", {"type": "3"}, lambda: order.append("third"))

        rm.shutdown_all()

        assert order == ["third", "second", "first"]

    def test_shutdown_idempotent(self):
        rm = ResourceManager()
        cleanup_count = []

        rm.register("db_pool", {"type": "pool"}, lambda: cleanup_count.append(1))

        rm.shutdown_all()
        rm.shutdown_all()

        assert cleanup_count == [1]

    def test_cleanup_error_does_not_stop_others(self):
        rm = ResourceManager()
        order = []

        def raise_on_cleanup():
            raise RuntimeError("boom")

        rm.register("first", {"type": "1"}, lambda: order.append("first"))
        rm.register("second", {"type": "2"}, raise_on_cleanup)
        rm.register("third", {"type": "3"}, lambda: order.append("third"))

        rm.shutdown_all()

        assert order == ["third", "first"]

    def test_thread_safety(self):
        rm = ResourceManager()
        errors = []

        def register_and_get(name):
            try:
                rm.register(name, {"name": name})
                for _ in range(10):
                    val = rm.get(name)
                    assert val is None or val["name"] == name
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=register_and_get, args=(f"r{i}",)) for i in range(20)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert not errors

    def test_health_integration(self):
        registry = HealthRegistry()
        rm = ResourceManager(health_registry=registry)

        rm.register("db_pool", {"type": "pool"})

        loop = asyncio.new_event_loop()
        try:
            results = loop.run_until_complete(registry.run_all())
            assert "resources" in results
            assert results["resources"].status == HealthStatus.HEALTHY
            assert "db_pool" in results["resources"].details["resources"]
        finally:
            loop.close()

    def test_health_after_shutdown(self):
        registry = HealthRegistry()
        rm = ResourceManager(health_registry=registry)

        rm.register("db_pool", {"type": "pool"})
        rm.shutdown_all()

        loop = asyncio.new_event_loop()
        try:
            results = loop.run_until_complete(registry.run_all())
            assert results["resources"].status == HealthStatus.DEGRADED
        finally:
            loop.close()


class TestAsyncResourceManager:
    """Tests for AsyncResourceManager."""

    def test_register_and_get(self):
        arm = AsyncResourceManager()
        resource = {"type": "pool"}
        arm.register("db_pool", resource)

        assert arm.get("db_pool") is resource
        assert arm.get("nonexistent") is None

    def test_register_duplicate_raises(self):
        arm = AsyncResourceManager()
        arm.register("db_pool", {"type": "pool"})

        with pytest.raises(ValueError, match="already registered"):
            arm.register("db_pool", {"type": "other"})

    @pytest.mark.asyncio
    async def test_acquire_yields_resource(self):
        arm = AsyncResourceManager()
        resource = {"type": "pool"}
        arm.register("db_pool", resource)

        async with arm.acquire("db_pool") as r:
            assert r is resource

    @pytest.mark.asyncio
    async def test_acquire_nonexistent_raises(self):
        arm = AsyncResourceManager()
        with pytest.raises(KeyError, match="not registered"):
            async with arm.acquire("nonexistent"):
                pass

    @pytest.mark.asyncio
    async def test_async_cleanup(self):
        arm = AsyncResourceManager()
        order = []

        async def cleanup_third():
            order.append("third")

        arm.register("first", {"type": "1"}, lambda: order.append("first"))
        arm.register("second", {"type": "2"}, lambda: order.append("second"))
        arm.register("third", {"type": "3"}, cleanup_third)

        await arm.shutdown_all()

        assert order == ["third", "second", "first"]

    @pytest.mark.asyncio
    async def test_shutdown_idempotent(self):
        arm = AsyncResourceManager()
        cleanup_count = []

        arm.register("db_pool", {"type": "pool"}, lambda: cleanup_count.append(1))

        await arm.shutdown_all()
        await arm.shutdown_all()

        assert cleanup_count == [1]

    @pytest.mark.asyncio
    async def test_cleanup_error_does_not_stop_others(self):
        arm = AsyncResourceManager()
        order = []

        def raise_on_cleanup():
            raise RuntimeError("boom")

        arm.register("first", {"type": "1"}, lambda: order.append("first"))
        arm.register("second", {"type": "2"}, raise_on_cleanup)
        arm.register("third", {"type": "3"}, lambda: order.append("third"))

        await arm.shutdown_all()

        assert order == ["third", "first"]

    def test_health_integration(self):
        registry = HealthRegistry()
        arm = AsyncResourceManager(health_registry=registry)

        arm.register("db_pool", {"type": "pool"})

        loop = asyncio.new_event_loop()
        try:
            results = loop.run_until_complete(registry.run_all())
            assert "async_resources" in results
            assert results["async_resources"].status == HealthStatus.HEALTHY
            assert "db_pool" in results["async_resources"].details["resources"]
        finally:
            loop.close()
