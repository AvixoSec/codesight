"""Provider factory."""

from __future__ import annotations

from collections.abc import Callable

from ..config import ProviderConfig
from .anthropic_provider import AnthropicProvider
from .base import BaseLLMProvider
from .google_provider import GoogleVertexProvider
from .openai_provider import OpenAIProvider

_REGISTRY: dict[str, Callable[[ProviderConfig], BaseLLMProvider]] = {
    "openai": OpenAIProvider,
    "anthropic": AnthropicProvider,
    "google": GoogleVertexProvider,
}


def create_provider(config: ProviderConfig) -> BaseLLMProvider:
    """Instantiate the correct provider based on configuration."""
    factory = _REGISTRY.get(config.provider)
    if factory is None:
        supported = ", ".join(_REGISTRY.keys())
        raise ValueError(
            f"Unknown provider '{config.provider}'. Supported: {supported}"
        )
    return factory(config)
