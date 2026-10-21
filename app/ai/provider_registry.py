from __future__ import annotations

import threading
from typing import Iterator
from app.ai.base_provider import BaseAIProvider


class ProviderRegistry:
    def __init__(self) -> None:
        self._providers: dict[str, BaseAIProvider] = {}
        self._lock = threading.RLock()

    def register(self, provider: BaseAIProvider) -> None:
        with self._lock:
            self._providers[provider.name.lower()] = provider

    def unregister(self, name: str) -> BaseAIProvider | None:
        with self._lock:
            return self._providers.pop(name.lower(), None)

    def get(self, name: str) -> BaseAIProvider | None:
        with self._lock:
            return self._providers.get(name.lower())

    def list_providers(self) -> list[BaseAIProvider]:
        with self._lock:
            return list(self._providers.values())

    def clear(self) -> None:
        with self._lock:
            self._providers.clear()

    def __iter__(self) -> Iterator[BaseAIProvider]:
        with self._lock:
            return iter(list(self._providers.values()))


_DEFAULT_REGISTRY = ProviderRegistry()


def get_default_registry() -> ProviderRegistry:
    return _DEFAULT_REGISTRY
