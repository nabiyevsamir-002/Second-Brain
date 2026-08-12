"""Provider reyestri — açar üzrə provayder saxlayır və verir.

İstifadə (gələcək fazalarda):
    from app.providers.registry import providers
    providers.register("llm", ClaudeLLMProvider(...))
    llm = providers.get("llm")
"""

from __future__ import annotations

from typing import Any


class ProviderRegistry:
    def __init__(self) -> None:
        self._providers: dict[str, Any] = {}

    def register(self, key: str, provider: Any) -> None:
        self._providers[key] = provider

    def get(self, key: str) -> Any:
        if key not in self._providers:
            raise KeyError(f"Provider qeydiyyatdan keçməyib: {key!r}")
        return self._providers[key]

    def has(self, key: str) -> bool:
        return key in self._providers


providers = ProviderRegistry()
