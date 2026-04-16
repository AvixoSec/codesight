import argparse
import asyncio
import json
import sys
from pathlib import Path

from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, MofNCompleteColumn
from rich.text import Text

from . import __version__
from .analyzer import Analyzer, AnalysisError, TaskType, collect_files
from .config import (
    AppConfig,
    CONFIG_FILE,
    ProviderConfig,
    load_config,
    save_config,
)

console = Console(stderr=True)
out = Console()

def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="codesight", description="Code analysis CLI")
    parser.add_argument("-v", "--version", action="version", version=f"codesight {__version__}")
    parser.add_argument("-p", "--provider", choices=["openai", "anthropic", "google"],
                      help="Provider to use")
    parser.add_argument("-o", "--output", choices=["markdown", "json", "plain"],
                      default=None, help="Output format")

    sub = parser.add_subparsers(dest="command")

    review = sub.add_parser("review", help="Review a file")
    review.add_argument("file")
    review.add_argument("-c", "--context", help="Extra context")

    bugs = sub.add_parser("bugs", help="Find bugs in a file")
    bugs.add_argument("file")
    bugs.add_argument("-c", "--context")

    docs = sub.add_parser("docs", help="Generate docs for a file")
    docs.add_argument("file")

    explain = sub.add_parser("explain", help="Explain a file")
    explain.add_argument("file")

    refactor = sub.add_parser("refactor", help="Refactor suggestions for a file")
    refactor.add_argument("file")

    scan = sub.add_parser("scan", help="Scan a directory")
    scan.add_argument("dir", nargs="?", default=".", help="Directory to scan (default: .)")
    scan.add_argument(
        "-t", "--task",
        choices=["review", "bugs"],
        default="review",
        help="Analysis type (default: review)",
    )
    scan.add_argument("--ext", nargs="*", help="File extensions to include (e.g. .py .js)")

    sub.add_parser("config", help="Configure CodeSight interactively")
    sub.add_parser("health", help="Check provider connectivity")

    return parser


def _format_output(result, fmt):
    h = Text()
    h.append(" CodeSight ", style="bold white on dark_green")
    h.append(f" {result.task.value.upper()} ", style="bold")
    h.append(f" {result.provider} ({result.model})", style="dim")

    t = Text(f"{result.tokens_used:,} tokens", style="dim")
    out.print(Panel(h, subtitle=t, border_style="green"))

    if fmt == "json":
        out.print_json(json.dumps(result.__dict__, default=str, indent=2))
    elif fmt == "plain":
        out.print(result.content)
    else:
        out.print(Markdown(result.content))
    out.print()


def _run_analysis(args, config: AppConfig) -> None:
    mapping = {"review": TaskType.REVIEW, "bugs": TaskType.BUGS,
               "docs": TaskType.DOCS, "explain": TaskType.EXPLAIN,
               "refactor": TaskType.REFACTOR}
    task = mapping[args.command]
    path = str(Path(args.file).resolve())

    try:
        analyzer = Analyzer(config, provider_name=args.provider)
    except ValueError as e:
        console.print(f"[red]Config error: {e}[/]")
        sys.exit(1)

    with console.status(f"[green]Analyzing {Path(path).name}...[/]", spinner="dots"):
        try:
            result = asyncio.run(analyzer.analyze_file(path, task,
                extra_context=getattr(args, "context", None)))
        except AnalysisError as e:
            console.print(f"[red]Failed: {e}[/]")
            sys.exit(1)

    _format_output(result, config.output_format)


def _run_scan(args, config: AppConfig) -> None:
    task = TaskType.REVIEW if args.task == "review" else TaskType.BUGS
    exts = {e if e.startswith(".") else f".{e}" for e in args.ext} if args.ext else None

    files = collect_files(
        args.dir,
        extensions=exts,
        ignore=config.ignore_patterns,
        max_size_kb=config.max_file_size_kb,
    )

    if not files:
        console.print("[yellow]No source files found.[/]")
        sys.exit(0)

    console.print(f"Found [bold]{len(files)}[/] files in [cyan]{Path(args.dir).resolve()}[/]")

    try:
        analyzer = Analyzer(config, provider_name=args.provider)
    except ValueError as exc:
        console.print(f"[bold red]Config error:[/] {exc}")
        sys.exit(1)

    results = []
    errors = []
    total_tokens = 0

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        MofNCompleteColumn(),
        console=console,
    ) as progress:
        scan_task = progress.add_task("Scanning...", total=len(files))

        for fp in files:
            short = str(Path(fp).relative_to(Path(args.dir).resolve()))
            progress.update(scan_task, description=f"[green]{short}[/]")
            try:
                result = asyncio.run(analyzer.analyze_file(fp, task))
                results.append(result)
                total_tokens += result.tokens_used
            except AnalysisError as exc:
                errors.append((fp, str(exc)))
            progress.advance(scan_task)

    for r in results:
        _format_output(r, config.output_format)

    summary = Text()
    summary.append(f"\n{len(results)} files analyzed", style="bold")
    if errors:
        summary.append(f", {len(errors)} failed", style="bold red")
    summary.append(f" — {total_tokens:,} tokens total", style="dim")
    out.print(Panel(summary, border_style="green", title="Scan Complete"))

    if errors:
        for fp, err in errors:
            console.print(f"  [red]✗[/] {fp}: {err}")


def _run_config() -> None:
    cfg = load_config()
    console.print(Panel("Configuration", border_style="cyan"))

    p = console.input(f"Provider [openai/anthropic/google] (now: {cfg.default_provider}): ").strip()
    p = p or cfg.default_provider
    cfg.default_provider = p

    if p == "openai":
        key = console.input("OpenAI API Key: ").strip()
        model = console.input("Model [gpt-5.4]: ").strip() or "gpt-5.4"
        cfg.providers["openai"] = ProviderConfig(provider="openai", api_key=key, model=model)
    elif p == "anthropic":
        key = console.input("Anthropic API Key: ").strip()
        model = console.input("Model [claude-opus-4-6]: ").strip() or "claude-opus-4-6-20251101"
        cfg.providers["anthropic"] = ProviderConfig(provider="anthropic", api_key=key, model=model)
    elif p == "google":
        project = console.input("Google Cloud Project: ").strip()
        region = console.input("Region [us-central1]: ").strip() or "us-central1"
        model = console.input("Model [gemini-3.1-pro]: ").strip() or "gemini-3.1-pro"
        cfg.providers["google"] = ProviderConfig(
            provider="google", project_id=project, region=region, model=model
        )
    else:
        console.print(f"[red]Unknown: {p}[/]")
        sys.exit(1)

    save_config(cfg)
    console.print(f"\n[green]Saved to {CONFIG_FILE}[/]")


def _run_health(args, config: AppConfig) -> None:
    try:
        a = Analyzer(config, provider_name=args.provider)
    except ValueError as e:
        console.print(f"[red]Config error: {e}[/]")
        sys.exit(1)

    with console.status("Checking...", spinner="dots"):
        ok = asyncio.run(a.health())

    if ok:
        console.print("[green]Provider OK[/]")
    else:
        console.print("[red]Provider unreachable[/]")
        sys.exit(1)


def main():
    parser = _build_parser()
    args = parser.parse_args()

    if not args.command:
        msg = f"codesight {__version__}\nRun: codesight --help"
        console.print(Panel(msg, border_style="green"))
        sys.exit(0)

    cfg = load_config()
    if args.output:
        cfg.output_format = args.output

    if args.command in ("review", "bugs", "docs", "explain", "refactor"):
        _run_analysis(args, cfg)
    elif args.command == "scan":
        _run_scan(args, cfg)
    elif args.command == "config":
        _run_config()
    elif args.command == "health":
        _run_health(args, cfg)


if __name__ == "__main__":
    main()
