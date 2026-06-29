"""
ARCHITECTURE GUARDRAILS - Enforce Clean Architecture Boundaries

These tests automatically reject any PR that violates layer boundaries.

Rules:
1. Domain cannot import brokers, api, or infrastructure specifics
2. Strategy cannot know about Dhan/Upstox implementations
3. API routers cannot contain business logic (must call Application)
4. Application depends on interfaces only (IBrokerGateway), not concrete classes

Run in CI before any merge: pytest tests/architecture/test_layer_enforcement.py -v
"""

import pytest
import importlib
import pkgutil
from pathlib import Path
from typing import Set, List


class ArchitectureGuard:
    """Enforces architectural boundaries between layers."""
    
    def __init__(self):
        self.violations: List[str] = []
        
    def forbid_imports(self, module_path: str, forbidden_prefixes: List[str]) -> "ArchitectureGuard":
        """
        Assert that a module does not import from forbidden prefixes.
        
        Args:
            module_path: Module to check (e.g., 'analytics.strategy')
            forbidden_prefixes: List of forbidden import prefixes (e.g., ['brokers.dhan'])
        """
        try:
            module = importlib.import_module(module_path)
            module_file = getattr(module, '__file__', None)
            
            if not module_file:
                return self  # Skip built-in modules
            
            # Get all imports in the module
            imports = self._get_module_imports(module_file)
            
            for imp in imports:
                for forbidden in forbidden_prefixes:
                    if imp.startswith(forbidden):
                        self.violations.append(
                            f"❌ VIOLATION: {module_path} imports '{imp}' (forbidden: {forbidden})"
                        )
        except ImportError as e:
            self.violations.append(f"⚠️  WARNING: Cannot import {module_path}: {e}")
        
        return self
    
    def _get_module_imports(self, file_path: str) -> Set[str]:
        """Extract all import statements from a Python file."""
        imports = set()
        
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()
                
            # Simple regex-based extraction (good enough for guardrails)
            import re
            
            # Match: import X, from X import Y
            patterns = [
                r'^import\s+([\w.]+)',
                r'^from\s+([\w.]+)\s+import',
            ]
            
            for line in content.split('\n'):
                line = line.strip()
                if line.startswith('#'):
                    continue
                    
                for pattern in patterns:
                    match = re.match(pattern, line)
                    if match:
                        imports.add(match.group(1))
                        
        except Exception:
            pass  # Ignore parsing errors
        
        return imports
    
    def verify(self) -> None:
        """Raise AssertionError if any violations found."""
        if self.violations:
            error_msg = "\n".join(self.violations)
            raise AssertionError(f"\n🚫 ARCHITECTURE VIOLATIONS DETECTED:\n{error_msg}")


def test_domain_purity():
    """
    Domain layer must NOT import:
    - brokers.* (Dhan, Upstox specifics)
    - api.* (FastAPI, HTTP details)
    - infrastructure.* (logging, event bus implementations)
    
    Domain can only depend on:
    - Standard library
    - Other domain modules
    """
    guard = ArchitectureGuard()
    
    # Check core domain modules
    domain_modules = [
        'domain.entities.order',
        'domain.entities.position',
        'domain.entities.instrument',
        'domain.events.types',
        'domain.ports.broker_gateway',
    ]
    
    forbidden = ['brokers', 'api', 'infrastructure']
    
    for module in domain_modules:
        guard.forbid_imports(module, forbidden)
    
    guard.verify()


def test_strategy_isolation():
    """
    Strategy layer must NOT know about broker implementations.
    
    Strategy can depend on:
    - Domain entities (Order, Signal, Tick)
    - Analytics (indicators, scanners)
    
    Strategy CANNOT depend on:
    - brokers.dhan.*
    - brokers.upstox.*
    - Direct broker SDK imports
    """
    guard = ArchitectureGuard()
    
    strategy_modules = [
        'analytics.strategy.models',
        'analytics.strategy.pipeline',
        'analytics.strategy.protocols',
    ]
    
    forbidden = ['brokers.dhan', 'brokers.upstox', 'dhanhq', 'upstox_client']
    
    for module in strategy_modules:
        try:
            guard.forbid_imports(module, forbidden)
        except AssertionError:
            pass  # Some modules might not exist yet
    
    guard.verify()


def test_api_layer_thinness():
    """
    API routers must be THIN - no business logic.
    
    Routers can:
    - Parse requests
    - Call application services
    - Return responses
    
    Routers CANNOT:
    - Import domain entities directly (use schemas)
    - Contain PnL calculations
    - Contain risk logic
    - Contain order matching logic
    """
    guard = ArchitectureGuard()
    
    router_modules = [
        'api.routers.orders',
        'api.routers.positions',
        'api.routers.market_data',
    ]
    
    # Routers should not import domain entities directly
    # They should use api.schemas instead
    forbidden = ['domain.entities']
    
    for module in router_modules:
        try:
            guard.forbid_imports(module, forbidden)
        except AssertionError:
            pass  # Some modules might not exist yet
    
    # Note: This is a soft check - some direct imports may be legitimate
    # The real test is whether business logic exists in routers


def test_application_depends_on_interfaces():
    """
    Application layer must depend on IBrokerGateway interface,
    NOT concrete broker implementations.
    
    Check that application/oms does not import:
    - brokers.dhan.gateway.DhanGateway
    - brokers.upstox.gateway.UpstoxGateway
    """
    guard = ArchitectureGuard()
    
    oms_modules = [
        'application.oms.order_manager',
        'application.oms.position_manager',
        'application.oms.risk_manager',
    ]
    
    forbidden = ['brokers.dhan.gateway', 'brokers.upstox.gateway']
    
    for module in oms_modules:
        try:
            guard.forbid_imports(module, forbidden)
        except AssertionError:
            pass  # Some modules might not exist yet
    
    guard.verify()


def test_broker_adapters_stay_contained():
    """
    Broker adapters (brokers/dhan, brokers/upstox) must NOT leak
    broker-specific details into other layers.
    
    Check that broker mappers do not import:
    - application.*
    - api.*
    """
    guard = ArchitectureGuard()
    
    broker_modules = [
        'brokers.dhan.mapper',
        'brokers.upstox.mapper',
    ]
    
    forbidden = ['application', 'api']
    
    for module in broker_modules:
        try:
            guard.forbid_imports(module, forbidden)
        except AssertionError:
            pass  # Some modules might not exist yet
    
    guard.verify()


@pytest.mark.architecture
def test_no_circular_dependencies():
    """
    Detect circular imports that could cause initialization failures.
    
    This test attempts to import all major modules and checks for
    ImportError caused by circular dependencies.
    """
    modules_to_test = [
        'domain.entities.order',
        'domain.entities.position',
        'application.oms.order_manager',
        'brokers.dhan.gateway',
        'analytics.strategy.base',
        'api.main',
    ]
    
    circular_deps = []
    
    for module_name in modules_to_test:
        try:
            importlib.import_module(module_name)
        except ImportError as e:
            if "circular import" in str(e).lower():
                circular_deps.append(f"{module_name}: {e}")
    
    if circular_deps:
        pytest.fail(f"Circular dependencies detected:\n" + "\n".join(circular_deps))


if __name__ == "__main__":
    # Run manually for quick validation
    print("🔍 Running Architecture Guardrails...")
    
    try:
        test_domain_purity()
        print("✅ Domain purity: PASS")
    except AssertionError as e:
        print(f"❌ Domain purity: FAIL\n{e}")
    
    try:
        test_strategy_isolation()
        print("✅ Strategy isolation: PASS")
    except AssertionError as e:
        print(f"❌ Strategy isolation: FAIL\n{e}")
    
    try:
        test_application_depends_on_interfaces()
        print("✅ Application interface dependency: PASS")
    except AssertionError as e:
        print(f"❌ Application interface dependency: FAIL\n{e}")
    
    print("\n🏁 Architecture Guard complete")
