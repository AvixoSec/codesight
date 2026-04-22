from ..config import ProviderConfig
from .anthropic_provider import AnthropicProvider
from .base import BaseLLMProvider
from .custom_provider import CustomProvider
from .google_provider import GoogleVertexProvider
from .ollama_provider import OllamaProvider
from .openai_provider import OpenAIProvider

_PROVIDERS = {
    "openai": OpenAIProvider,
    "anthropic": AnthropicProvider,
    "google": GoogleVertexProvider,
    "ollama": OllamaProvider,
    "custom": CustomProvider,
}


def create_provider(config: ProviderConfig) -> BaseLLMProvider:
    factory = _PROVIDERS.get(config.provider)
    if factory is None:
        if config.base_url:
            return CustomProvider(config)
        supported = ", ".join(_PROVIDERS)
        raise ValueError(
            f"Unknown provider '{config.provider}'. Supported: {supported}"
        )
    return factory(config)
