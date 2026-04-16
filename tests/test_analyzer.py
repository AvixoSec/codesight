"""Analyzer tests."""

import asyncio
from unittest.mock import AsyncMock, patch, MagicMock

import pytest

from codesight.analyzer import Analyzer, TaskType, SYSTEM_PROMPTS
from codesight.config import AppConfig, ProviderConfig
from codesight.providers.base import LLMResponse


@pytest.fixture
def mock_config():
    return AppConfig(
        default_provider="openai",
        providers={
            "openai": ProviderConfig(provider="openai", api_key="test-key"),
        },
    )


@pytest.fixture
def mock_provider():
    provider = AsyncMock()
    provider.name = "MockProvider"
    provider.complete.return_value = LLMResponse(
        content="## Summary\nAll looks good.",
        model="gpt-5.4-test",
        usage={"prompt_tokens": 100, "completion_tokens": 50},
        provider="MockProvider",
    )
    return provider


def test_system_prompts_exist_for_all_tasks():
    for task in TaskType:
        assert task in SYSTEM_PROMPTS
        assert len(SYSTEM_PROMPTS[task]) > 50


def test_analyze_file(mock_config, mock_provider, tmp_path):
    test_file = tmp_path / "sample.py"
    test_file.write_text("def add(a, b):\n    return a + b\n")

    with patch("codesight.analyzer.create_provider", return_value=mock_provider):
        analyzer = Analyzer(mock_config)
        result = asyncio.run(analyzer.analyze_file(str(test_file), TaskType.REVIEW))

    assert result.task == TaskType.REVIEW
    assert result.content == "## Summary\nAll looks good."
    assert result.tokens_used == 150
    mock_provider.complete.assert_called_once()
