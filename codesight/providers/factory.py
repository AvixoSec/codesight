from ..config import ProviderConfig
from .anthropic_provider import AnthropicProvider
from .base import BaseLLMProvider
from .google_provider import GoogleVertexProvider
from .openai_provider import OpenAIProvider

_PROVIDERS = {
    "openai": OpenAIProvider,
    "anthropic": AnthropicProvider,
    "google": GoogleVertexProvider,
}


def create_provider(config):
    factory = _PROVIDERS.get(config.provider)
    if factory is None:
        supported = ", ".join(_PROVIDERS)
        raise ValueError(
            f"Unknown provider '{config.provider}'. Supported: {supported}"
        )
    return factory(config)
