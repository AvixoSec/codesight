from codesight.config import ProviderConfig
from codesight.providers.custom_provider import CustomProvider


def test_openrouter_does_not_send_http_referer_by_default():
    provider = CustomProvider(
        ProviderConfig(
            provider="custom",
            api_key="test-key",
            base_url="https://openrouter.ai/api/v1",
            model="meta-llama/llama-4-maverick",
        )
    )

    assert "HTTP-Referer" not in provider._headers
    assert provider._headers["X-Title"] == "CodeSight"
