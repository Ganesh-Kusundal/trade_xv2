"""Generic registry base class."""
from __future__ import annotations
from typing import TypeVar, Generic

T = TypeVar('T')

class Registry(Generic[T]):
    """Base registry with register/get/has/keys/values/items."""
    
    def __init__(self) -> None:
        self._items: dict[str, T] = {}
    
    def register(self, name: str, item: T) -> None:
        self._items[name] = item
    
    def get(self, name: str) -> T | None:
        return self._items.get(name)
    
    def has(self, name: str) -> bool:
        return name in self._items
    
    def keys(self) -> list[str]:
        return list(self._items.keys())
    
    def values(self) -> list[T]:
        return list(self._items.values())
    
    def items(self) -> list[tuple[str, T]]:
        return list(self._items.items())
    
    def __len__(self) -> int:
        return len(self._items)
    
    def __contains__(self, name: str) -> bool:
        return self.has(name)
