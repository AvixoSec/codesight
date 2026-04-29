import asyncio
from unittest.mock import AsyncMock, patch

import pytest

from codesight.analyzer import SYSTEM_PROMPTS, Analyzer, TaskType, collect_files
from codesight.config import AppConfig, ProviderConfig
from codesight.providers.base import LLMResponse, Message


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


def test_complete_messages_uses_analyzer_defaults(mock_config, mock_provider):
    with patch("codesight.analyzer.create_provider", return_value=mock_provider):
        analyzer = Analyzer(mock_config)
        asyncio.run(
            analyzer.complete_messages(
                [
                    Message(role="system", content="sys"),
                    Message(role="user", content="hello"),
                ]
            )
        )

    mock_provider.complete.assert_called_once_with(
        [
            Message(role="system", content="sys"),
            Message(role="user", content="hello"),
        ],
        max_tokens=4096,
        temperature=0.2,
    )


def test_collect_files_finds_source_files(tmp_path):
    (tmp_path / "main.py").write_text("print(1)")
    (tmp_path / "utils.py").write_text("def helper(): pass")
    (tmp_path / "data.txt").write_text("not a source file")

    files = collect_files(str(tmp_path))

    assert len(files) == 2
    assert any("main.py" in f for f in files)
    assert any("utils.py" in f for f in files)


def test_collect_files_ignores_hidden_and_ignore_patterns(tmp_path):
    hidden = tmp_path / ".git"
    hidden.mkdir()
    (hidden / "config.py").write_text("a = 1")

    node = tmp_path / "node_modules"
    node.mkdir()
    (node / "lib.js").write_text("module.exports = {};")

    (tmp_path / "app.py").write_text("print(1)")

    files = collect_files(str(tmp_path), ignore=["node_modules"])

    assert len(files) == 1


def test_collect_files_filter_by_extension(tmp_path):
    (tmp_path / "script.py").write_text("pass")
    (tmp_path / "main.go").write_text("package main")
    (tmp_path / "app.rs").write_text("fn main() {}")

    files = collect_files(str(tmp_path), extensions={".py", ".rs"})

    assert len(files) == 2
    assert any(".py" in f for f in files)
    assert any(".rs" in f for f in files)
    assert not any("main.go" in f for f in files)


def test_collect_files_skip_large_files(tmp_path):
    (tmp_path / "small.py").write_text("x = 1")
    big = tmp_path / "large.py"
    big.write_text("x = 1\n" * 10000)  # ~70KB

    files = collect_files(str(tmp_path), max_size_kb=50)

    assert len(files) == 1
    assert "small.py" in files[0]
