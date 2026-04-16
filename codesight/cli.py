"""CLI entry point."""

import argparse
import asyncio
import sys
from pathlib import Path

from . import __version__
from .analyzer import Analyzer, TaskType
from .config import (
    AppConfig,
    ProviderConfig,
    load_config,
    save_config,
)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="codesight",
        description="AI-powered code analysis and review tool",
    )
    parser.add_argument("-v", "--version", action="version", version=f"codesight {__version__}")
    parser.add_argument(
        "-p", "--provider",
        choices=["openai", "anthropic", "google"],
        help="LLM provider to use (overrides config default)",
    )
    parser.add_argument(
        "-o", "--output",
        choices=["markdown", "json", "plain"],
        default=None,
        help="Output format",
    )

    sub = parser.add_subparsers(dest="command")

    # Analysis commands
    for cmd in ("review", "bugs", "docs", "explain", "refactor"):
        p = sub.add_parser(cmd, help=f"Run {cmd} analysis on a file")
        p.add_argument("file", help="Path to the source file")
        p.add_argument("-c", "--context", help="Extra context for the analysis")

    # Config command
    sub.add_parser("config", help="Configure CodeSight interactively")

    # Health check
    sub.add_parser("health", help="Check provider connectivity")

    return parser


def _run_analysis(args, config: AppConfig) -> None:
    task_map = {
        "review": TaskType.REVIEW,
        "bugs": TaskType.BUGS,
        "docs": TaskType.DOCS,
        "explain": TaskType.EXPLAIN,
        "refactor": TaskType.REFACTOR,
    }
    task = task_map[args.command]
    file_path = str(Path(args.file).resolve())

    if not Path(file_path).is_file():
        print(f"Error: file not found — {file_path}", file=sys.stderr)
        sys.exit(1)

    analyzer = Analyzer(config, provider_name=args.provider)
    result = asyncio.run(analyzer.analyze_file(
        file_path,
        task,
        extra_context=getattr(args, "context", None),
    ))

    print(f"\n{'='*60}")
    print(f"  CodeSight | {result.task.value.upper()} | {result.provider} ({result.model})")
    print(f"  Tokens used: {result.tokens_used}")
    print(f"{'='*60}\n")
    print(result.content)


def _run_config() -> None:
    config = load_config()
    print("CodeSight Configuration")
    print("-" * 40)

    provider = input("Default provider [openai/anthropic/google] (current: {}): ".format(
        config.default_provider
    )).strip() or config.default_provider
    config.default_provider = provider

    if provider == "openai":
        key = input("OpenAI API Key: ").strip()
        model = input("Model [gpt-5.4]: ").strip() or "gpt-5.4"
        config.providers["openai"] = ProviderConfig(
            provider="openai", api_key=key, model=model,
        )
    elif provider == "anthropic":
        key = input("Anthropic API Key: ").strip()
        model = input("Model [claude-opus-4-6-20251101]: ").strip() or "claude-opus-4-6-20251101"
        config.providers["anthropic"] = ProviderConfig(
            provider="anthropic", api_key=key, model=model,
        )
    elif provider == "google":
        project = input("Google Cloud Project ID: ").strip()
        region = input("Region [us-central1]: ").strip() or "us-central1"
        model = input("Model [gemini-3.1-pro]: ").strip() or "gemini-3.1-pro"
        config.providers["google"] = ProviderConfig(
            provider="google", project_id=project, region=region, model=model,
        )

    save_config(config)
    print(f"\n✓ Configuration saved to {config}")


def _run_health(args, config: AppConfig) -> None:
    analyzer = Analyzer(config, provider_name=args.provider)
    ok = asyncio.run(analyzer.health())
    if ok:
        print("✓ Provider is reachable and healthy.")
    else:
        print("✗ Could not reach the provider. Check your credentials.", file=sys.stderr)
        sys.exit(1)


def main() -> None:
    parser = _build_parser()
    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(0)

    config = load_config()
    if args.output:
        config.output_format = args.output

    if args.command in ("review", "bugs", "docs", "explain", "refactor"):
        _run_analysis(args, config)
    elif args.command == "config":
        _run_config()
    elif args.command == "health":
        _run_health(args, config)


if __name__ == "__main__":
    main()
