"""Provider factory."""

from ..config import ProviderConfig
from .base import BaseLLMProvider
from .openai_provider import OpenAIProvider
from .anthropic_provider import AnthropicProvider
from .google_provider import GoogleVertexProvider

_REGISTRY = {
    "openai": OpenAIProvider,
    "anthropic": AnthropicProvider,
    "google": GoogleVertexProvider,
}


def create_provider(config: ProviderConfig) -> BaseLLMProvider:
    """Instantiate the correct provider based on configuration."""
    cls = _REGISTRY.get(config.provider)
    if cls is None:
        supported = ", ".join(_REGISTRY.keys())
        raise ValueError(
            f"Unknown provider '{config.provider}'. Supported: {supported}"
        )
    return cls(config)
