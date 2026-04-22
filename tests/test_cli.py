from types import SimpleNamespace

import pytest

import codesight.cli as cli_module
from codesight.cli import (
    _is_valid_template_name,
    _mask_identifier,
    _mask_url_display,
    _parse_pipeline_arg,
    _result_exit_code,
)
from codesight.config import AppConfig


def test_parse_pipeline_arg_allows_colons_and_slashes_in_model_names():
    parsed = _parse_pipeline_arg(
        "custom/meta-llama/Llama-3-70b-chat-hf:anthropic/claude-opus-4-7"
    )

    assert parsed == (
        "custom",
        "meta-llama/Llama-3-70b-chat-hf",
        "anthropic",
        "claude-opus-4-7",
    )


def test_parse_pipeline_arg_splits_on_last_colon_only():
    parsed = _parse_pipeline_arg("ollama/llama3:8b:openai/gpt-5.4")

    assert parsed == ("ollama", "llama3:8b", "openai", "gpt-5.4")


def test_parse_pipeline_arg_requires_colon_separator():
    with pytest.raises(ValueError):
        _parse_pipeline_arg("ollama/llama3")


def test_is_valid_template_name_accepts_safe_slugs():
    assert _is_valid_template_name("quick-review_2") is True


def test_is_valid_template_name_rejects_path_traversal():
    assert _is_valid_template_name("../../etc/passwd") is False


def test_mask_identifier_redacts_middle_characters():
    assert _mask_identifier("my-secret-project") == "my-s...ject"


def test_mask_url_display_preserves_path_and_masks_host():
    masked = _mask_url_display(
        "https://my-resource.services.ai.azure.com/anthropic/v1/messages"
    )

    assert masked == "https://my-...rce.services.ai.azure.com/anthropic/v1/messages"


def test_result_exit_code_ignores_plain_severity_words_without_findings():
    content = "## Summary\nNo critical issues found. High level architecture looks fine."

    assert _result_exit_code(content, "sample.py") == 0


def test_result_exit_code_uses_bracketed_warning_markers_without_findings():
    content = "## Summary\n[WARN] Review suggested safer validation for user input."

    assert _result_exit_code(content, "sample.py") == 1


def test_result_exit_code_uses_structured_findings():
    content = (
        "## Security Findings\n"
        "### [HIGH] SQL Injection — CWE-89\n"
        "**Location:** sample.py:12\n"
        "**Description:** Untrusted input reaches SQL.\n"
        "**Fix:** Use parameterized queries.\n"
    )

    assert _result_exit_code(content, "sample.py") == 1


def test_result_exit_code_does_not_fallback_to_warn_when_findings_exist():
    content = (
        "## Security Findings\n"
        "### [LOW] Verbose Error Message — CWE-209\n"
        "**Location:** sample.py:12\n"
        "**Description:** Returned errors expose extra context.\n"
        "**Fix:** Return generic failures to callers.\n"
        "\n## Notes\nLiteral marker [WARN] in docs should not change exit code.\n"
    )

    assert _result_exit_code(content, "sample.py") == 0


def test_run_interactive_skips_scan_when_directory_prompt_is_cancelled(monkeypatch):
    config = AppConfig()
    select_answers = iter(["scan", "quit"])
    run_scan_calls = []

    monkeypatch.setattr(cli_module, "load_config", lambda: config)
    monkeypatch.setattr(
        cli_module.questionary,
        "select",
        lambda *args, **kwargs: SimpleNamespace(ask=lambda: next(select_answers)),
    )
    monkeypatch.setattr(
        cli_module.questionary,
        "path",
        lambda *args, **kwargs: SimpleNamespace(ask=lambda: None),
    )
    monkeypatch.setattr(
        cli_module,
        "_run_scan",
        lambda *args, **kwargs: run_scan_calls.append((args, kwargs)),
    )

    cli_module._run_interactive(config)

    assert run_scan_calls == []


def test_run_interactive_skips_scan_when_task_prompt_is_cancelled(monkeypatch):
    config = AppConfig()
    select_answers = iter(["scan", None, "quit"])
    run_scan_calls = []

    monkeypatch.setattr(cli_module, "load_config", lambda: config)
    monkeypatch.setattr(
        cli_module.questionary,
        "select",
        lambda *args, **kwargs: SimpleNamespace(ask=lambda: next(select_answers)),
    )
    monkeypatch.setattr(
        cli_module.questionary,
        "path",
        lambda *args, **kwargs: SimpleNamespace(ask=lambda: "."),
    )
    monkeypatch.setattr(
        cli_module,
        "_run_scan",
        lambda *args, **kwargs: run_scan_calls.append((args, kwargs)),
    )

    cli_module._run_interactive(config)

    assert run_scan_calls == []
