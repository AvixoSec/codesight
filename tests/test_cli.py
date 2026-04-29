from types import SimpleNamespace

import pytest

import codesight.cli as cli_module
from codesight.cli import (
    _ask_verify_wizard_args,
    _build_parser,
    _is_valid_template_name,
    _mask_identifier,
    _mask_url_display,
    _parse_context_lines,
    _parse_pipeline_arg,
    _result_exit_code,
    _verify_exit_code,
)
from codesight.config import AppConfig
from codesight.findings import VerifiedFinding


def test_parse_pipeline_arg_allows_colons_and_slashes_in_model_names():
    parsed = _parse_pipeline_arg("custom/meta-llama/Llama-3-70b-chat-hf:anthropic/claude-opus-4-7")

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
    masked = _mask_url_display("https://my-resource.services.ai.azure.com/anthropic/v1/messages")

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


def test_parser_accepts_provider_and_output_after_security_command():
    parser = _build_parser()

    args = parser.parse_args(["security", "app.py", "--provider", "ollama", "--output", "json"])

    assert args.command == "security"
    assert args.provider == "ollama"
    assert args.output == "json"


def test_parser_accepts_provider_and_output_after_scan_command():
    parser = _build_parser()

    args = parser.parse_args(
        ["scan", ".", "--provider", "ollama", "--task", "security", "--output", "sarif"]
    )

    assert args.command == "scan"
    assert args.provider == "ollama"
    assert args.output == "sarif"


def test_parser_accepts_judge_flags_after_verify_command():
    parser = _build_parser()

    args = parser.parse_args(
        [
            "verify",
            "semgrep.sarif",
            "--source",
            ".",
            "--judge",
            "--skeptic",
            "--preview-context",
            "--profile",
            "flask",
            "--provider",
            "ollama",
            "--output",
            "json",
        ]
    )

    assert args.command == "verify"
    assert args.judge is True
    assert args.skeptic is True
    assert args.preview_context is True
    assert args.profile == "flask"
    assert args.provider == "ollama"
    assert args.output == "json"


def test_parser_opens_guided_ui_command():
    parser = _build_parser()

    assert parser.parse_args(["ui"]).command == "ui"
    assert parser.parse_args(["wizard"]).command == "wizard"


def test_parse_context_lines_falls_back_to_default():
    assert _parse_context_lines("12") == 12
    assert _parse_context_lines("-5") == 0
    assert _parse_context_lines("bad") == 20


def test_verify_wizard_builds_bundle_args(monkeypatch):
    config = AppConfig()
    path_answers = iter(["scanner.sarif", ".", "proof"])
    select_answers = iter(["bundle", "flask", "json", "never"])

    monkeypatch.setattr(
        cli_module.questionary,
        "path",
        lambda *args, **kwargs: SimpleNamespace(ask=lambda: next(path_answers)),
    )
    monkeypatch.setattr(
        cli_module.questionary,
        "select",
        lambda *args, **kwargs: SimpleNamespace(ask=lambda: next(select_answers)),
    )
    monkeypatch.setattr(
        cli_module.questionary,
        "text",
        lambda *args, **kwargs: SimpleNamespace(ask=lambda: "12"),
    )

    args = _ask_verify_wizard_args(config, provider_name=None)

    assert args is not None
    assert args.sarif == "scanner.sarif"
    assert args.profile == "flask"
    assert args.context_lines == 12
    assert args.output == "json"
    assert args.fail_on == "never"
    assert args.artifact_dir == "proof"
    assert args.judge is False


def test_verify_exit_code_does_not_fail_on_uncertain_by_default():
    finding = VerifiedFinding(
        id="CS-VFY-001",
        title="Imported scanner alert",
        verdict="uncertain",
        severity="high",
        confidence="medium",
        file_path="app.py",
        start_line=1,
    )

    assert _verify_exit_code([finding], "exploitable") == 0
    assert _verify_exit_code([finding], "uncertain") == 1


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
