import pytest

from codesight.config import AppConfig, ProviderConfig
from codesight.streaming import stream_analysis


@pytest.mark.asyncio
async def test_stream_analysis_unknown_provider():
    config = AppConfig(
        default_provider="unknown_provider",
        providers={
            "unknown_provider": ProviderConfig(
                provider="unknown_provider",
                api_key="x",
            ),
        },
    )
    with pytest.raises(ValueError, match="not supported"):
        async for _ in stream_analysis(config, [{"role": "user", "content": "hi"}]):
            pass


def test_stream_module_imports():
    from codesight.streaming import (
        stream_anthropic,
        stream_ollama,
        stream_openai,
    )
    assert callable(stream_openai)
    assert callable(stream_anthropic)
    assert callable(stream_ollama)
